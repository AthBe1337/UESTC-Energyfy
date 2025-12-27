import requests
import execjs
from bs4 import BeautifulSoup
import re
import json
from utils.Logger import get_logger

class RoomInfo:

    def __init__(self, username, password):
        self.USERNAME = username
        self.PASSWORD = password
        self.BASE_URL = "https://idas.uestc.edu.cn"
        self.EPORTAL_BASE_URL = "https://portal.uestc.edu.cn"
        self.LOGIN_URL = f"{self.BASE_URL}/authserver/login"
        self.TARGET_URL = f"{self.EPORTAL_BASE_URL}/qljfwapp/sys/lwUestcDormElecPrepaid/index.do#/record"
        self.INFO_API = f"{self.EPORTAL_BASE_URL}/qljfwapp/sys/lwUestcDormElecPrepaid/dormElecPrepaidMan/queryRoomInfo.do"
        self.logger = get_logger()

        self.logger.debug("[RoomInfo] 初始化 -> 用户名: %s", username)

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
        except Exception as e:
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
            except requests.exceptions.RequestException as e:
                raise RuntimeError("重定向请求失败") from e

        # 超出最大重定向次数
        raise RuntimeError(f"超过最大重定向次数 ({max_redirects})")


    def login(self):
        """
        执行登录流程并返回最终响应和会话信息
        :return: (最终响应对象, cookies字典, 重定向历史列表)
        :raises RuntimeError: 初始化环境失败、登录失败或请求异常时抛出
        """
        self.logger.debug("[RoomInfo.login] 开始执行登录流程")
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        }
        session.headers.update(headers)

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
            self.logger.debug("[RoomInfo.login] 提取 execution: %s", execution)

            salt_input = soup.find('input', {'id': 'pwdEncryptSalt'})
            salt = salt_input.get('value') if salt_input else "rjBFAaHsNkKAhpoi"
            self.logger.debug("[RoomInfo.login] 提取 salt: %s", salt)

            # 加密密码
            encrypted_pwd = js_ctx.call("encryptPasswordForPython", self.PASSWORD, salt)
        except Exception as e:
            raise RuntimeError("初始化登录环境失败") from e

        # 构造登录载荷
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

        self.logger.debug("[RoomInfo.login] 构造登录载荷: %s", payload)

        try:
            # 提交登录请求（禁用重定向）
            login_response = session.post(self.LOGIN_URL, data=payload, allow_redirects=False)
            self.logger.debug("[RoomInfo.login] 登录响应状态码: %s", login_response.status_code)
            login_response.raise_for_status()

            # 检查登录响应
            if login_response.status_code not in (301, 302, 303, 307, 308):
                raise RuntimeError(f"登录失败! 状态码: {login_response.status_code}")

            # 获取重定向URL
            if 'Location' not in login_response.headers:
                raise RuntimeError("登录响应缺少重定向Location头")

            redirect_url = login_response.headers['Location']
            self.logger.debug("[RoomInfo.login] 登录重定向URL: %s", redirect_url)

            # 跟随重定向链
            final_response, redirect_history = self.follow_redirects(session, redirect_url)
            self.logger.debug("[RoomInfo.login] 最终响应URL: %s", final_response.url)

            # 返回最终响应、重定向历史和所有cookie
            return final_response, session.cookies.get_dict(), redirect_history
        except requests.exceptions.RequestException as e:
            raise RuntimeError("登录请求失败") from e

    def get(self, queries):
        """
        根据宿舍ID查询电费信息
        :param queries: 宿舍ID列表或可迭代对象
        :return: [(宿舍ID字符串, 宿舍信息字典或None), ...]
        :raises RuntimeError: 登录失败、请求失败或响应异常时抛出
        """
        self.logger.debug("[RoomInfo.get] 开始查询宿舍列表: %s", queries)
        try:
            final_response, cookies, redirect_history = self.login()

            if not final_response or not cookies:
                raise RuntimeError("登录失败，未获取有效会话")

            # 构造批量 roomIds 参数
            room_ids_list = [{"DORM_ID": str(q)} for q in queries]
            payload = {
                "roomIds": json.dumps(room_ids_list, ensure_ascii=False)
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
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
            result = []

            for query, item in zip(queries, response_list):
                room_info = item.get('roomInfo', {})
                if room_info.get('retcode') == 0:
                    self.logger.debug("[RoomInfo.get] 宿舍 %s 查询成功 -> 余额: %s", query, room_info.get("syje"))
                    result.append((str(query), room_info))
                else:
                    self.logger.debug("[RoomInfo.get] 宿舍 %s 查询失败: %s", query, room_info.get("msg"))
                    self.logger.warning(f"RoomInfo: 获取宿舍 {query} 信息失败: {room_info.get('msg')}")
                    result.append((str(query), None))

            return result

        except requests.exceptions.RequestException as e:
            raise RuntimeError("宿舍信息请求失败") from e
        except Exception as e:
            raise RuntimeError("获取宿舍信息时出错") from e

