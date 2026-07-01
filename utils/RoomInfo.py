import requests
import execjs
from bs4 import BeautifulSoup
import re
import json
import logging
import os
import hashlib
import secrets
import io

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from utils.Logger import get_logger
    from utils import __version__
except ImportError:
    # 当被其他项目调用时，使用 NullHandler 禁用日志输出
    def get_logger():
        logger = logging.getLogger("RoomInfo")
        logger.addHandler(logging.NullHandler())
        return logger
    __version__ = "1.3.0"


class TwoFactorRequired(Exception):
    """登录后需要二次认证"""
    def __init__(self, reauth_url, session, message="需要二次认证"):
        self.reauth_url = reauth_url
        self.session = session
        self.message = message
        super().__init__(message)


class RoomInfo:

    def __init__(self, username, password, logger=None, bfp=None,
                 verify_code_handler=None, seed=None):
        """
        初始化 RoomInfo 对象

        :param username: 用户名
        :param password: 密码
        :param logger: 可选的自定义日志器
        :param bfp: 可选，浏览器指纹（MULTIFACTOR_BROWSER_FINGERPRINT cookie 值）。
                    如果提供且设备已被信任，可跳过二次认证。
        :param verify_code_handler: 可选，当需要二次认证时调用的函数，
                                    接收消息字符串，返回验证码字符串。
                                    如果为 None 且需要二次认证，则抛出 TwoFactorRequired
        :param seed: 可选，BFP 种子字符串。如果提供，将用于生成确定性的浏览器指纹
                    （替换浏览器标识中的随机部分）；如果为 None，则使用随机字符串，
                    保证每次 --verify 生成的 BFP 唯一。
        """
        self.USERNAME = username
        self.PASSWORD = password
        self.BASE_URL = "https://idas.uestc.edu.cn"
        self.PORTAL_BASE_URL = "https://portal.uestc.edu.cn"
        self.LOGIN_URL = f"{self.BASE_URL}/authserver/login"
        self.TARGET_URL = f"{self.PORTAL_BASE_URL}/qljfwapp/sys/lwUestcDormElecPrepaid/index.do#/record"
        self.INFO_API = f"{self.PORTAL_BASE_URL}/qljfwapp/sys/lwUestcDormElecPrepaid/dormElecPrepaidMan/queryRoomInfo.do"
        self.logger = logger if logger is not None else get_logger()
        self.bfp = bfp
        self.verify_code_handler = verify_code_handler
        self.seed = seed

        self._reauth_session = None
        self._reauth_params = None
        self._new_bfp = bfp

        self.logger.debug("[RoomInfo] 初始化 -> 用户名: %s, bfp: %s",
                          self.USERNAME,
                          self.bfp[:16] + "..." if self.bfp else "无")

    def _create_session(self):
        """创建 requests.Session 并设置浏览器请求头"""
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }
        session.headers.update(headers)
        return session

    def _compute_fingerprint(self):
        """在 Python 中复现 common-header.js 的浏览器指纹算法。
        指纹 = MD5(browser|engine|os|cpu|device|model|vendor|platform|
                    language|cores|touch|memory|canvasMD5)
        canvas 部分用 Pillow 复现，其余匹配 Chrome 120 on Linux。

        browser 标识使用 seed 或随机字符串，确保每次 --verify 生成
        的 BFP 唯一，避免所有用户共享同一指纹。
        """
        if not HAS_PIL:
            raise RuntimeError("需要 Pillow 库来计算浏览器指纹")

        canvas = Image.new('RGB', (220, 30), 'white')
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([112, 1, 112 + 62, 1 + 20], fill='#f60')
        txt = 'WiseduCiap,com <canvas> 1.0'
        try:
            font = ImageFont.truetype(
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
        except Exception:
            font = ImageFont.load_default()
        draw.text((2, 13), txt, fill='#069', font=font)
        draw.text((4, 15), txt, fill=(102, 204, 0), font=font)

        buf = io.BytesIO()
        canvas.save(buf, format='PNG')
        canvas_md5 = hashlib.md5(buf.getvalue()).hexdigest().upper()

        # 使用 seed 或随机字符串作为浏览器标识，保证 BFP 唯一性
        browser_ident = ('Energyfy-' + self.seed) if self.seed \
            else 'Energyfy-' + secrets.token_hex(8)

        items = [
            browser_ident, 'Blink', 'Linux', 'amd64', '', '', '',
            'Linux x86_64', 'zh-CN', '8', '0', '8',
            canvas_md5,
        ]
        return hashlib.md5('|'.join(items).encode()).hexdigest().upper()

    def _ensure_bfp(self, session):
        """确保 session 有 MULTIFACTOR_BROWSER_FINGERPRINT cookie。
        如果已有 bfp 则直接设置，否则计算新指纹并提交到服务器。"""
        if self._new_bfp:
            session.cookies.set(
                'MULTIFACTOR_BROWSER_FINGERPRINT', self._new_bfp,
                domain='idas.uestc.edu.cn', path='/'
            )
            self.logger.debug("[RoomInfo] 使用已有 bfp: %s...", self._new_bfp[:16])
            return

        fingerprint = self._compute_fingerprint()
        self.logger.debug("[RoomInfo] 指纹计算完成: %s", fingerprint)
        try:
            session.post(
                f"{self.BASE_URL}/authserver/bfp/info",
                data={'bfp': fingerprint},
                headers={
                    'Referer': self.LOGIN_URL,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                }
            )
            bfp = session.cookies.get('MULTIFACTOR_BROWSER_FINGERPRINT')
            if bfp:
                self._new_bfp = bfp
                self.logger.debug("[RoomInfo] 新 bfp 已获取: %s...", bfp[:16])
        except Exception as e:
            self.logger.warning("[RoomInfo] 指纹提交失败: %s", e)

    def get_session_state(self):
        """返回当前可持久化的 bfp 值"""
        return {'bfp': self._new_bfp} if self._new_bfp else None

    def get_dynamic_js(self, session):
        """
        从登录页面动态获取加密JS代码
        :param session: 已创建的 requests.Session 对象
        :return: 加密JS代码字符串
        :raises RuntimeError: 无法找到加密JS文件或请求失败时抛出
        """
        self.logger.debug("[RoomInfo.get_dynamic_js] 请求登录页: %s", self.LOGIN_URL)
        try:
            login_page = session.get(self.LOGIN_URL)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, 'html.parser')

            # 查找加密JS的script标签
            js_script = soup.find('script', {'src': re.compile(r'/authserver/uestcTheme/static/common/encrypt\.js\?v=.*')})
            if not js_script:
                raise RuntimeError("无法找到加密JS文件")

            js_url = self.BASE_URL + js_script['src']
            self.logger.debug("[RoomInfo.get_dynamic_js] 解析到JS文件URL: %s", js_url)

            js_response = session.get(js_url)
            js_response.raise_for_status()
            self.logger.debug("[RoomInfo.get_dynamic_js] 成功获取加密JS，长度: %s", len(js_response.text))
            return js_response.text
        except requests.exceptions.RequestException as e:
            raise RuntimeError("请求加密JS失败") from e
        except Exception as e:
            raise RuntimeError("获取动态JS时出错") from e


    def create_js_context(self, js_code):
        """
        创建加密JS的执行环境
        :param js_code: 从页面获取的加密JS代码
        :return: execjs 编译后的执行上下文对象
        :raises RuntimeError: JS 编译失败时抛出
        """
        self.logger.debug("[RoomInfo.create_js_context] 编译加密JS...")
        # 添加暴露给Python的辅助函数
        js_code += """
        // 暴露给Python调用的函数
        function encryptPasswordForPython(password, salt) {
            return encryptPassword(password, salt);
        }
        """
        try:
            ctx = execjs.compile(js_code)
            self.logger.debug("[RoomInfo.create_js_context] 编译成功 (默认环境)")
            return ctx
        except Exception:
            try:
                ctx = execjs.get("Node").compile(js_code)
                self.logger.debug("[RoomInfo.create_js_context] 编译成功 (Node 环境)")
                return ctx
            except Exception as e2:
                raise RuntimeError("JS 编译错误（默认环境和 Node 都失败）") from e2


    def follow_redirects(self, session, start_url, max_redirects=10):
        """
        手动跟随HTTP重定向链
        :param session: requests.Session 对象
        :param start_url: 起始URL
        :param max_redirects: 最大重定向次数（默认10）
        :return: (最终响应对象, 重定向历史列表)
        :raises RuntimeError: 请求失败、缺少Location头或超过最大重定向次数时抛出
        """
        current_url = start_url
        redirect_count = 0
        redirect_history = []

        self.logger.debug("[RoomInfo.follow_redirects] 起始URL: %s", start_url)

        while redirect_count < max_redirects:
            try:
                # 发送请求（禁用自动重定向）
                response = session.get(current_url, allow_redirects=False)
                response.raise_for_status()

                # 记录重定向历史
                redirect_history.append({
                    'url': current_url,
                    'status': response.status_code,
                    'headers': dict(response.headers),
                    'cookies': session.cookies.get_dict()
                })

                # 检查是否是重定向
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_count += 1
                    self.logger.debug("[RoomInfo.follow_redirects] 第 %s 次重定向: %s", redirect_count, current_url)
                    if 'Location' in response.headers:
                        # 处理相对路径URL
                        location = response.headers['Location']
                        if not location.startswith('http'):
                            if location.startswith('/'):
                                location = self.BASE_URL + location
                            else:
                                # 从当前URL解析基础路径
                                base_url = '/'.join(current_url.split('/')[:3])
                                location = base_url + '/' + location
                        current_url = location
                    else:
                        raise RuntimeError("重定向响应缺少Location头")
                else:
                    # 非重定向响应，返回最终结果
                    self.logger.debug("[RoomInfo.follow_redirects] 最终URL: %s", current_url)
                    return response, redirect_history
            except Exception as e:
                raise RuntimeError("重定向请求失败") from e

        # 超出最大重定向次数
        raise RuntimeError(f"超过最大重定向次数 ({max_redirects})")

    def _is_2fa_redirect(self, url):
        """检测是否是二次认证页面"""
        return 'reAuthCheck/reAuthLoginView.do' in url

    def _parse_reauth_page(self, response):
        """解析二次认证页面，提取 reAuthParams"""
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tags = soup.find_all('script')
        reauth_params = {}

        for script in script_tags:
            if script.string and 'reAuthParams' in script.string:
                match = re.search(
                    r'var\s+reAuthParams\s*=\s*({.*?});', script.string, re.DOTALL)
                if match:
                    js_obj = match.group(1)
                    for item in re.finditer(
                            r'"(\w+)"\s*:\s*("(?:[^"\\]|\\.)*"|[^,}\]]+)', js_obj):
                        key = item.group(1)
                        val = item.group(2).strip().strip('"')
                        # 反转义 JS 字符串中的 \/ → /
                        val = val.replace(r'\/', '/')
                        reauth_params[key] = val
                    break

        return reauth_params

    def _reauth_headers(self):
        """2FA API 请求所需的 HTTP 头"""
        return {
            'Referer': f"{self.BASE_URL}/authserver/reAuthCheck/reAuthLoginView.do?isMultifactor=true",
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        }

    def send_verify_code(self):
        """发送短信验证码。"""
        if not self._reauth_session:
            raise RuntimeError("没有活动的二次认证会话，请先调用 login()")

        session = self._reauth_session
        params = self._reauth_params
        headers = self._reauth_headers()

        self.logger.debug("[RoomInfo] 切换到短信验证码模式 (reAuthType=3)")
        change_resp = session.post(
            f"{self.BASE_URL}/authserver/reAuthCheck/changeReAuthType.do",
            data={
                'isMultifactor': params.get('isMultifactor', 'true'),
                'reAuthType': '3',
                'service': params.get('service', ''),
            },
            headers=headers,
        )
        self.logger.debug("[RoomInfo] changeReAuthType 响应: %s",
                          change_resp.text[:200])

        self.logger.debug("[RoomInfo] 发送短信验证码...")
        send_resp = session.post(
            f"{self.BASE_URL}/authserver/dynamicCode/getDynamicCodeByReauth.do",
            data={
                'userName': params.get('reAuthUserId', self.USERNAME),
                'authCodeTypeName': 'reAuthDynamicCodeType',
            },
            headers=headers,
        )
        self.logger.debug("[RoomInfo] 发送验证码响应: %s", send_resp.text[:500])

        try:
            result = send_resp.json()
        except ValueError:
            raise RuntimeError(f"发送验证码响应异常: {send_resp.text[:200]}")

        if result.get('res') == 'success':
            mobile = result.get('mobile', '')
            msg = result.get('returnMessage', '验证码已发送')
            full_msg = f"{msg}{mobile}"
            self.logger.info("[RoomInfo] 验证码已发送: %s", full_msg)
            return full_msg
        elif result.get('res') == 'code_time_fail':
            wait = result.get('codeTime', 60)
            msg = result.get('returnMessage', f'请{wait}秒后再试')
            raise RuntimeError(f"发送验证码过于频繁: {msg}")
        else:
            msg = result.get('returnMessage', '发送失败')
            raise RuntimeError(f"发送验证码失败: {msg}")

    def submit_verify_code(self, code, trust_device=True):
        """提交验证码完成二次认证。
        :param code: 短信验证码
        :param trust_device: 是否信任此设备（下次免二次认证）
        :return: (final_response, cookies_dict, redirect_history, session_state)
        """
        if not self._reauth_session:
            raise RuntimeError("没有活动的二次认证会话")

        session = self._reauth_session
        params = self._reauth_params

        submit_data = {
            'service': params.get('service', ''),
            'reAuthType': '3',
            'isMultifactor': params.get('isMultifactor', 'true'),
            'password': '',
            'dynamicCode': code,
            'uuid': '',
            'answer1': '',
            'answer2': '',
            'otpCode': '',
            'skipTmpReAuth': 'true' if trust_device else 'false',
        }

        self.logger.debug("[RoomInfo] 提交二次认证, trust_device=%s", trust_device)
        submit_resp = session.post(
            f"{self.BASE_URL}/authserver/reAuthCheck/reAuthSubmit.do",
            data=submit_data,
            allow_redirects=False,
            headers=self._reauth_headers(),
        )
        self.logger.debug("[RoomInfo] reAuthSubmit 响应: status=%s, body=%s",
                          submit_resp.status_code, submit_resp.text[:500])

        try:
            result = submit_resp.json()
            if result.get('code') in ('reAuth_failed', 'reAuth_unauthorized'):
                raise RuntimeError(f"二次认证失败: {result.get('msg', '未知错误')}")
        except ValueError:
            pass

        final_response, redirect_history = self.follow_redirects(
            session,
            f"{self.BASE_URL}/authserver/login?service={params.get('service', '')}"
        )

        self._new_bfp = session.cookies.get('MULTIFACTOR_BROWSER_FINGERPRINT')
        cookies_dict = session.cookies.get_dict()
        session_state = {'bfp': self._new_bfp}

        self.logger.debug("[RoomInfo] 二次认证完成，最终URL: %s", final_response.url)
        return final_response, cookies_dict, redirect_history, session_state

    def login(self):
        """执行登录流程。
        :return: (final_response, cookies_dict, redirect_history, session_state)
        :raises TwoFactorRequired: 需要二次认证但没有设置 verify_code_handler
        """
        self.logger.debug("[RoomInfo.login] 开始执行登录流程")
        session = self._create_session()

        try:
            # 获取动态JS代码
            js_content = self.get_dynamic_js(session)
            js_ctx = self.create_js_context(js_content)

            # 重新获取登录页面
            login_page = session.get(self.TARGET_URL)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, 'html.parser')

            # 提取参数
            execution = soup.find('input', {'name': 'execution'})
            if not execution:
                raise ValueError("无法找到execution参数")
            execution = execution.get('value', '')
            self.logger.debug("[RoomInfo.login] 提取 execution: %s", execution[:80])

            salt_input = soup.find('input', {'id': 'pwdEncryptSalt'})
            salt = salt_input.get('value') if salt_input else "rjBFAaHsNkKAhpoi"
            self.logger.debug("[RoomInfo.login] 提取 salt: %s", salt)

            # 加密密码
            encrypted_pwd = js_ctx.call("encryptPasswordForPython", self.PASSWORD, salt)
        except Exception as e:
            raise RuntimeError("初始化登录环境失败") from e

        # 设置浏览器指纹 cookie
        self._ensure_bfp(session)

        payload = {
            'username': self.USERNAME,
            'password': encrypted_pwd,
            'captcha': '',
            '_eventId': 'submit',
            'cllt': 'userNameLogin',
            'dllt': 'generalLogin',
            'lt': '',
            'execution': execution
        }

        # 添加隐藏字段
        for input_tag in soup.select('input[type="hidden"]'):
            name = input_tag.get('name')
            if name and name not in payload:
                payload[name] = input_tag.get('value', '')

        self.logger.debug("[RoomInfo.login] 提交登录请求...")

        try:
            # 提交登录请求（禁用重定向）
            login_response = session.post(login_page.url, data=payload, allow_redirects=False)
            self.logger.debug("[RoomInfo.login] 登录响应状态码: %s", login_response.status_code)

            # 检查登录响应
            if login_response.status_code not in (301, 302, 303, 307, 308):
                if login_response.status_code == 401:
                    raise RuntimeError("登录失败: 账号或密码错误，或账号已被冻结")
                raise RuntimeError(f"登录失败! 状态码: {login_response.status_code}")

            # 获取重定向URL
            if 'Location' not in login_response.headers:
                raise RuntimeError("登录响应缺少重定向Location头")

            redirect_url = login_response.headers['Location']
            self.logger.debug("[RoomInfo.login] 登录重定向URL: %s", redirect_url)

            if self._is_2fa_redirect(redirect_url):
                self.logger.info("[RoomInfo.login] 检测到二次认证页面")

                self._reauth_session = session
                reauth_page = session.get(redirect_url, allow_redirects=False)
                self._reauth_params = self._parse_reauth_page(reauth_page)

                if self.verify_code_handler:
                    msg = self.send_verify_code()
                    self.logger.info("[RoomInfo.login] 等待验证码输入...")
                    code = self.verify_code_handler(msg)
                    return self.submit_verify_code(code, trust_device=True)
                else:
                    raise TwoFactorRequired(
                        reauth_url=redirect_url,
                        session=session,
                        message="需要二次认证（短信验证码），请运行 --verify"
                    )

            # 无二次认证，直接跟随重定向
            final_response, redirect_history = self.follow_redirects(
                session, redirect_url)
            self.logger.debug("[RoomInfo.login] 最终响应URL: %s", final_response.url)

            self._new_bfp = session.cookies.get('MULTIFACTOR_BROWSER_FINGERPRINT')
            cookies_dict = session.cookies.get_dict()
            session_state = {'bfp': self._new_bfp}

            return final_response, cookies_dict, redirect_history, session_state

        except TwoFactorRequired:
            raise
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"登录请求失败: {e}") from e

    def get(self, queries):
        """
        根据宿舍ID查询电费信息
        :param queries: 宿舍ID列表或可迭代对象
        :return: [(宿舍ID字符串, 宿舍信息字典或None), ...]
        :raises RuntimeError: 登录失败、请求失败或响应异常时抛出
        """
        queries_list = list(queries)  # 将可迭代对象转换为列表
        self.logger.debug("[RoomInfo.get] 开始查询宿舍列表: %s", queries_list)
        
        try:
            login_result = self.login()
            if len(login_result) == 4:
                final_response, cookies, redirect_history, session_state = login_result
            else:
                final_response, cookies, redirect_history = login_result

            if not final_response or not cookies:
                raise RuntimeError("登录失败，未获取有效会话")

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }

            result = []
            batch_size = 50  # 每批最多50个请求
            
            # 分段处理查询
            if len(queries_list) > batch_size:
                self.logger.debug("[RoomInfo.get] 查询数量 %s 超过 %s，进行分段请求", len(queries_list), batch_size)
                
                # 分段发送请求
                for i in range(0, len(queries_list), batch_size):
                    batch_queries = queries_list[i:i + batch_size]
                    self.logger.debug("[RoomInfo.get] 发送第 %s 批请求，包含 %s 个宿舍", 
                                     i // batch_size + 1, len(batch_queries))
                    
                    # 构造批量 roomIds 参数
                    room_ids_list = [{"DORM_ID": str(q)} for q in batch_queries]
                    payload = {
                        "roomIds": json.dumps(room_ids_list, ensure_ascii=False)
                    }
                    
                    # 发送请求
                    response = requests.post(
                        self.INFO_API,
                        data=payload,
                        headers=headers,
                        cookies=cookies
                    )
                    response.raise_for_status()

                    response_list = response.json()
                    
                    # 处理该批次的响应
                    for query, item in zip(batch_queries, response_list):
                        room_info = item.get('roomInfo', {})
                        if room_info.get('retcode') == 0:
                            self.logger.debug("[RoomInfo.get] 宿舍 %s 查询成功 -> 余额: %s", query, room_info.get("syje"))
                            result.append((str(query), room_info))
                        else:
                            self.logger.debug("[RoomInfo.get] 宿舍 %s 查询失败: %s", query, room_info.get("msg"))
                            self.logger.warning(f"RoomInfo: 获取宿舍 {query} 信息失败: {room_info.get('msg')}")
                            result.append((str(query), None))
            else:
                # 一次性发送所有请求
                room_ids_list = [{"DORM_ID": str(q)} for q in queries_list]
                payload = {
                    "roomIds": json.dumps(room_ids_list, ensure_ascii=False)
                }

                # 发送请求
                response = requests.post(
                    self.INFO_API,
                    data=payload,
                    headers=headers,
                    cookies=cookies
                )
                response.raise_for_status()

                response_list = response.json()

                for query, item in zip(queries_list, response_list):
                    room_info = item.get('roomInfo', {})
                    if room_info.get('retcode') == 0:
                        self.logger.debug("[RoomInfo.get] 宿舍 %s 查询成功 -> 余额: %s", query, room_info.get("syje"))
                        result.append((str(query), room_info))
                    else:
                        self.logger.debug("[RoomInfo.get] 宿舍 %s 查询失败: %s", query, room_info.get("msg"))
                        self.logger.warning(f"RoomInfo: 获取宿舍 {query} 信息失败: {room_info.get('msg')}")
                        result.append((str(query), None))

            return result

        except TwoFactorRequired:
            raise
        except Exception as e:
            raise RuntimeError("获取宿舍信息时出错") from e
