import requests
import execjs
from bs4 import BeautifulSoup
import re

class RoomInfo:

    def __init__(self, username, password):
        self.USERNAME = username
        self.PASSWORD = password
        self.BASE_URL = "https://idas.uestc.edu.cn"
        self.EPORTAL_BASE_URL = "https://eportal.uestc.edu.cn"
        self.LOGIN_URL = f"{self.BASE_URL}/authserver/login"
        self.TARGET_URL = f"{self.EPORTAL_BASE_URL}/qljfwapp/sys/lwUestcDormElecPrepaid/index.do#/record"
        self.INFO_API = f"{self.EPORTAL_BASE_URL}/qljfwapp/sys/lwUestcDormElecPrepaid/dormElecPrepaidMan/queryRoomInfo.do"


    def get_dynamic_js(self, session):
        """从登录页面动态获取加密JS URL并下载内容"""
        try:
            login_page = session.get(self.LOGIN_URL)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, 'html.parser')

            # 查找加密JS的script标签
            js_script = soup.find('script', {'src': re.compile(r'/authserver/uestcTheme/static/common/encrypt\.js\?v=.*')})
            if not js_script:
                raise RuntimeError("无法找到加密JS文件")

            js_url = self.BASE_URL + js_script['src']
            js_response = session.get(js_url)
            js_response.raise_for_status()

            return js_response.text
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"请求失败: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"获取动态JS时出错: {str(e)}")


    def create_js_context(self, js_code):
        """创建JS执行环境"""
        # 添加暴露给Python的辅助函数
        js_code += """
        // 暴露给Python调用的函数
        function encryptPasswordForPython(password, salt) {
            return encryptPassword(password, salt);
        }
        """
        try:
            return execjs.compile(js_code)
        except Exception as e:
            try:
                return execjs.get("Node").compile(js_code)
            except Exception as e2:
                raise RuntimeError(f"JS编译错误: {str(e)} 和 {str(e2)}")


    def follow_redirects(self, session, start_url, max_redirects=10):
        """跟随重定向链直到获得最终响应"""
        current_url = start_url
        redirect_count = 0
        redirect_history = []

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
                    return response, redirect_history
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"重定向请求失败: {str(e)}")

        # 超出最大重定向次数
        raise RuntimeError(f"超过最大重定向次数 ({max_redirects})")


    def login(self):
        """执行登录流程并处理重定向链"""
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

            salt_input = soup.find('input', {'id': 'pwdEncryptSalt'})
            salt = salt_input.get('value') if salt_input else "rjBFAaHsNkKAhpoi"

            # 加密密码
            encrypted_pwd = js_ctx.call("encryptPasswordForPython", self.PASSWORD, salt)
        except Exception as e:
            raise RuntimeError(f"初始化错误: {str(e)}")

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

        try:
            # 提交登录请求（禁用重定向）
            login_response = session.post(self.LOGIN_URL, data=payload, allow_redirects=False)
            login_response.raise_for_status()

            # 检查登录响应
            if login_response.status_code not in (301, 302, 303, 307, 308):
                raise RuntimeError(f"登录失败! 状态码: {login_response.status_code}")

            # 获取重定向URL
            if 'Location' not in login_response.headers:
                raise RuntimeError("登录响应缺少重定向Location头")

            redirect_url = login_response.headers['Location']

            # 跟随重定向链
            final_response, redirect_history = self.follow_redirects(session, redirect_url)

            # 返回最终响应、重定向历史和所有cookie
            return final_response, session.cookies.get_dict(), redirect_history
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"登录请求失败: {str(e)}")

    def get(self, queries):
        try:
            final_response, cookies, redirect_history = self.login()

            if not final_response or not cookies:
                raise RuntimeError("登录失败")

            result = []

            for query in queries:
                payload = {
                    "roomIds": f'[{{"DORM_ID":"{str(query)}"}}]'
                }

                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                }

                response = requests.post(
                    self.INFO_API,
                    data=payload,
                    headers=headers,
                    cookies=cookies
                )
                response.raise_for_status()

                response_json = response.json()[0]['roomInfo']

                if response_json['retcode'] == 0:
                    result.append((str(query), response_json))

            return result
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"请求发生错误: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"获取宿舍信息时出错: {str(e)}")