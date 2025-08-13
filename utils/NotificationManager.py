import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import json

class NotificationManager:
    def __init__(self, email_host=None, email_port=None, encryption='none',
                 email_username=None, email_password=None, email_sender=None):
        """
        初始化通知管理器
        :param email_host: SMTP服务器地址
        :param email_port: SMTP端口
        :param encryption: 加密方式 ('ssl', 'tls', 'none')
        :param email_username: SMTP用户名
        :param email_password: SMTP密码
        :param email_sender: 发件人邮箱
        """
        self.email_config = {
            'host': email_host,
            'port': email_port,
            'encryption': encryption,
            'username': email_username,
            'password': email_password,
            'sender': email_sender
        }

    def send_email(self, recipients, subject, text_content=None, html_content=None):
        """
        发送电子邮件通知，支持纯文本和HTML格式
        :param recipients: 收件人邮箱(字符串或列表)
        :param subject: 邮件主题
        :param text_content: 纯文本格式的邮件内容
        :param html_content: HTML格式的邮件内容
        :return: 发送成功返回True
        :raises: ValueError - 当配置不完整或参数无效时
        :raises: RuntimeError - 当发送过程中出现错误时
        """
        # 检查邮件配置是否完整
        missing_configs = [k for k, v in self.email_config.items() if v is None]
        if missing_configs:
            raise ValueError(f"邮件配置不完整，缺少以下参数: {', '.join(missing_configs)}")

        # 验证内容参数
        if not text_content and not html_content:
            raise ValueError("必须提供 text_content 或 html_content 至少一种内容格式")

        # 验证收件人参数
        if not recipients:
            raise ValueError("收件人列表不能为空")

        # 收件人格式处理
        if isinstance(recipients, str):
            recipients = [recipients]
        elif not isinstance(recipients, list):
            raise TypeError("收件人必须是字符串或字符串列表")

        # 创建邮件对象
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.email_config['sender']
        msg['To'] = ', '.join(recipients)

        # 添加邮件正文内容
        if text_content:
            part1 = MIMEText(text_content, 'plain', 'utf-8')
            msg.attach(part1)

        if html_content:
            part2 = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part2)

        try:
            # 根据加密方式创建连接
            if self.email_config['encryption'] == 'ssl':
                server = smtplib.SMTP_SSL(
                    self.email_config['host'],
                    self.email_config['port']
                )
            else:
                server = smtplib.SMTP(
                    self.email_config['host'],
                    self.email_config['port']
                )
                if self.email_config['encryption'] == 'tls':
                    server.starttls()

            # 登录并发送
            server.login(
                self.email_config['username'],
                self.email_config['password']
            )
            server.sendmail(
                self.email_config['sender'],
                recipients,
                msg.as_string()
            )
            server.quit()
            return True
        except smtplib.SMTPException as e:
            raise RuntimeError(f"SMTP协议错误: {str(e)}") from e
        except TimeoutError as e:
            raise RuntimeError(f"连接邮件服务器超时: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"邮件发送失败: {str(e)}") from e

    def send_server_chan(self, uid, sendkey, title=None, text=None,
                         desp=None, tags=None, short=None):
        """
        发送Server酱通知
        :param uid: 用户UID
        :param sendkey: 发送密钥
        :param title: 消息标题
        :param text: 消息文本(当title不存在时作为标题)
        :param desp: 详细内容(Markdown格式)
        :param tags: 标签(多个用|分隔)
        :param short: 简短描述
        :return: 成功返回响应JSON
        :raises: ValueError - 当参数无效时
        :raises: RuntimeError - 当发送过程中出现错误时
        """
        # 参数校验
        if not title and not text:
            raise ValueError("必须提供 title 或 text 参数")
        if not uid or not sendkey:
            raise ValueError("uid 和 sendkey 不能为空")

        # 构建请求URL
        url = f"https://{uid}.push.ft07.com/send/{sendkey}.send"

        # 准备请求数据
        payload = {}
        if title:
            payload['title'] = title
        elif text:
            payload['title'] = text  # 当title不存在时使用text作为标题

        if desp:
            payload['desp'] = desp
        if tags:
            payload['tags'] = tags
        if short:
            payload['short'] = short

        # 发送请求
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                timeout=10
            )
            response.raise_for_status()  # 检查HTTP错误
            return response.json()
        except requests.exceptions.HTTPError as e:
            # 提取服务器返回的错误信息
            try:
                error_detail = e.response.json().get('message', '无详细错误信息')
            except:
                error_detail = e.response.text
            raise RuntimeError(f"Server酱推送失败: HTTP错误 {e.response.status_code} - {error_detail}") from e
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"网络连接错误: {str(e)}") from e
        except requests.exceptions.Timeout as e:
            raise RuntimeError(f"请求超时: {str(e)}") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"请求异常: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"Server酱推送失败: {str(e)}") from e
