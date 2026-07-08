import json
import random
import requests
import time
import logging

try:
    from utils.Logger import get_logger
except ImportError:
    # 当被其他项目调用时，使用 NullHandler 禁用日志输出
    def get_logger():
        logger = logging.getLogger("RoomInfo")
        logger.addHandler(logging.NullHandler())
        return logger


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_HOST = "wx.weiweixiao.net"
DEFAULT_ORIGIN = f"http://{DEFAULT_HOST}"

# API 固定参数
API_TOKEN = "usgMkdVR6BGAAAAWPwAVGQ"
API_ID = "skIWNmy96BGAAAAWPwAVGQ"

ITEM_LIST_PATH = "/index.php/Wap/ModZhjf/itemList.html"
QUERY_ITEM_PATH = "/index.php/Wap/ModZhjf/queryItem.html"
CONFIRM_PATH = "/index.php/Wap/ModZhjf/confirm.html"
UNBIND_PATH_TPL = "/index.php/Wap/ModZhjf/unbind/token/{token}/id/{id}.html"

# 伪装成微信 Windows 客户端
WECHAT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "NetType/WIFI MicroMessenger/7.0.20.1781 WindowsWechat XWEB/20005"
)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class RoomInfoError(RuntimeError):
    """RoomInfo 通用运行时错误"""


class CookieExpiredError(RoomInfoError):
    """Cookie 已过期或无效"""


# ---------------------------------------------------------------------------
# RoomInfo
# ---------------------------------------------------------------------------

class RoomInfo:
    """
    电子科技大学宿舍电费查询客户端（WeiWeiXiao 微信平台版）。

    通过用户提供的 Cookie 和学工号访问 wx.weiweixiao.net，
    支持房间绑定同步和余额查询。

    用法::

        ri = RoomInfo(cookie="...", xgh="2021001001")
        ri.sync(["114514", "225678"], mode="strict")
        results = ri.query_balances(["114514", "225678"])
    """

    def __init__(self, cookie, xgh, host=DEFAULT_HOST, logger=None,
                 on_set_cookie=None):
        """
        :param cookie: wx.weiweixiao.net 的 Cookie 字符串
        :param xgh:    学工号（str）、逗号分隔字符串、或列表，绑定房间时随机选择
        :param host:   WeiWeiXiao 服务器域名
        :param logger: 可选的自定义日志器
        :param on_set_cookie: 可选回调，当服务器返回 Set-Cookie 时调用，
                              签名为 on_set_cookie(new_cookie: str) -> None
        """
        if not cookie or not cookie.strip():
            raise ValueError("cookie 不能为空")

        # 规范化 xgh：统一存为列表
        if isinstance(xgh, str):
            xgh = [x.strip() for x in xgh.split(",") if x.strip()]
        if not xgh:
            raise ValueError("xgh 不能为空")
        self.xgh_list = [str(x).strip() for x in xgh]

        self.cookie = cookie.strip()
        self.xgh = self.xgh_list[0]  # 初始默认值
        self.host = host
        self.origin = f"http://{host}"
        self.logger = logger if logger is not None else get_logger()
        self.on_set_cookie = on_set_cookie
        self.cookie_expired = False

        # 使用 API 固定常量
        self.token = API_TOKEN
        self.zhjf_id = API_ID

        # 构造 Referer URL
        self.item_list_url = (
            f"http://{host}/index.php/Wap/ModZhjf/"
            f"itemList/token/{self.token}/id/{self.zhjf_id}.html"
        )

        # 创建会话
        self._session = self._create_session()

        self.logger.debug("[RoomInfo] 初始化 -> host: %s, xgh 候选: %s, token: %s, id: %s",
                         self.host, self.xgh_list, self.token, self.zhjf_id)

    # ---- Session ------------------------------------------------------------

    def _create_session(self):
        """创建带有 Cookie 和微信 UA 的 requests.Session"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": WECHAT_UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        for part in self.cookie.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                session.cookies.set(key.strip(), value.strip(),
                                    domain=self.host, path="/")
        return session

    def _pick_xgh(self):
        """从 xgh 列表中随机选择一个。"""
        self.xgh = random.choice(self.xgh_list)
        return self.xgh

    def _handle_set_cookie(self, response):
        """检查响应中的 Set-Cookie 头，合并到本地 cookie 并调用回调。"""
        set_cookies = response.headers.get("Set-Cookie", "")
        if not set_cookies:
            return

        # 解析 cookie 字符串，逐个合并或替换
        current = dict(
            part.split("=", 1) for part in self.cookie.split("; ")
            if "=" in part
        )
        for item in set_cookies.split(","):
            item = item.strip()
            if "=" in item:
                # 只取第一个 ; 之前的部分（去掉 path/domain 等属性）
                pair = item.split(";", 1)[0].strip()
                key, value = pair.split("=", 1)
                current[key.strip()] = value.strip()

        new_cookie = "; ".join(f"{k}={v}" for k, v in current.items())
        self.cookie = new_cookie

        # 同步到 session
        for part in new_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                self._session.cookies.set(key.strip(), value.strip(),
                                          domain=self.host, path="/")

        self.logger.info("[RoomInfo] Cookie 已更新（服务器返回了 Set-Cookie）")
        if self.on_set_cookie:
            self.on_set_cookie(new_cookie)

    # ---- API 请求 -----------------------------------------------------------

    def _query_item(self, page_no=1):
        """调用 queryItem API 获取已绑定房间列表和余额。"""
        url = f"{self.origin}{QUERY_ITEM_PATH}"
        params = {
            "page_no": str(page_no),
            "token": self.token,
            "id": self.zhjf_id,
            "_": str(int(time.time() * 1000)),
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.item_list_url,
        }

        self.logger.debug("[RoomInfo._query_item] GET page=%s", page_no)

        try:
            resp = self._session.get(url, params=params, headers=headers,
                                     timeout=20)
        except requests.RequestException as e:
            raise RuntimeError(f"queryItem 请求失败: {e}") from e

        self._handle_set_cookie(resp)

        try:
            data = resp.json()
        except ValueError:
            self.logger.error("[RoomInfo._query_item] 非 JSON 响应: %s",
                              resp.text[:500])
            raise RuntimeError("queryItem 返回了非 JSON 响应，Cookie 可能已过期")

        ret_code = data.get("ret_code")
        self.logger.debug("[RoomInfo._query_item] ret_code=%s, full: %s",
                          ret_code, json.dumps(data, ensure_ascii=False))

        # 检测认证失败
        if ret_code is None or (isinstance(ret_code, int) and ret_code != 0):
            ret_content_str = str(data.get("ret_content", ""))
            if (ret_code == -1 or "login" in ret_content_str.lower()
                    or "auth" in ret_content_str.lower()):
                self.cookie_expired = True
                self.logger.error("[RoomInfo._query_item] Cookie 已过期 (ret_code=%s)",
                                  ret_code)
                return []

        content = data.get("ret_content", [])
        if isinstance(content, dict):
            content = list(content.values())
        elif not isinstance(content, list):
            content = []
        return content

    def _bind_room(self, room_name):
        """POST confirm 绑定一个房间。"""
        xgh = self._pick_xgh()
        url = f"{self.origin}{CONFIRM_PATH}"
        form = {
            "id": self.zhjf_id,
            "token": self.token,
            "pay_type": "1",
            "item_list[0][total_fee]": "0.01",
            "item_list[0][room_name]": room_name,
            "item_list[0][phone]": "",
            "item_list[0][xgh]": xgh,
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.item_list_url,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.origin,
        }

        self.logger.info("[RoomInfo._bind_room] 绑定房间: %s (xgh=%s)",
                         room_name, xgh)

        try:
            resp = self._session.post(url, data=form, headers=headers,
                                      timeout=20)
        except requests.RequestException as e:
            self.logger.error("[RoomInfo._bind_room] 请求失败: %s", e)
            return False

        self._handle_set_cookie(resp)

        try:
            data = resp.json()
        except ValueError:
            self.logger.error("[RoomInfo._bind_room] 非 JSON 响应: %s",
                              resp.text[:300])
            return False

        ret_code = data.get("ret_code")
        if ret_code == 0:
            self.logger.info("[RoomInfo._bind_room] 绑定成功: %s", room_name)
            return True
        else:
            self.logger.warning("[RoomInfo._bind_room] 绑定失败 %s: ret_code=%s, msg=%s",
                                room_name, ret_code, data.get("ret_content", ""))
            return False

    def _unbind_room(self, room_name):
        """POST unbind 解绑一个房间。"""
        url = f"{self.origin}{UNBIND_PATH_TPL.format(token=self.token, id=self.zhjf_id)}"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.item_list_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        self.logger.info("[RoomInfo._unbind_room] 解绑房间: %s", room_name)

        try:
            resp = self._session.post(url, data={"plugin_param": room_name},
                                      headers=headers, timeout=20)
        except requests.RequestException as e:
            self.logger.error("[RoomInfo._unbind_room] 请求失败: %s", e)
            return False

        self._handle_set_cookie(resp)

        try:
            data = resp.json()
        except ValueError:
            self.logger.error("[RoomInfo._unbind_room] 非 JSON 响应: %s",
                              resp.text[:300])
            return False

        ret_code = data.get("ret_code")
        if ret_code == 0:
            self.logger.info("[RoomInfo._unbind_room] 解绑成功: %s", room_name)
            return True
        else:
            self.logger.warning("[RoomInfo._unbind_room] 解绑失败 %s: ret_code=%s, msg=%s",
                                room_name, ret_code, data.get("ret_content", ""))
            return False

    # ---- 余额提取 -----------------------------------------------------------

    @staticmethod
    def _extract_balance(room_data):
        """从 queryItem 返回的 room 对象中提取余额。"""
        value = room_data.get("syje")
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
        return None

    # ---- 公开 API -----------------------------------------------------------

    def check_health(self):
        """快速检查 Cookie 是否有效。

        :return: True 表示 Cookie 有效
        """
        try:
            items = self._query_item(page_no=1)
            return not self.cookie_expired
        except Exception as e:
            self.logger.warning("[RoomInfo.check_health] 健康检查失败: %s", e)
            return False

    def query_balances(self, room_names):
        """查询指定房间的电费余额。

        :param room_names: 房间名列表
        :return: [(room_name, info_dict | None), ...]
                 info_dict 包含 "syje"（余额字符串）和 "retcode"（0 表示成功）
        """
        queries = [str(r) for r in room_names]
        self.logger.debug("[RoomInfo.query_balances] 查询房间: %s", queries)
        items = self._query_item(page_no=1)

        if self.cookie_expired:
            return [(q, None) for q in queries]

        server_map = {}
        for item in items:
            if isinstance(item, dict) and item.get("roomName"):
                server_map[str(item["roomName"])] = item

        result = []
        for name in queries:
            if name in server_map:
                balance = self._extract_balance(server_map[name])
                if balance is not None:
                    info = {"syje": str(balance), "retcode": 0}
                    self.logger.debug("[RoomInfo.query_balances] %s -> 余额: %s",
                                      name, balance)
                else:
                    info = {"syje": "0.0", "retcode": -1}
                    self.logger.warning("[RoomInfo.query_balances] %s 无法提取余额: %s",
                                        name, server_map[name])
                result.append((name, info))
            else:
                self.logger.warning("[RoomInfo.query_balances] %s 未在已绑定列表中找到",
                                    name)
                result.append((name, None))

        return result

    def get_remote_bindings(self):
        """获取服务端当前绑定的房间名集合。"""
        items = self._query_item(page_no=1)
        bound = set()
        for item in items:
            if isinstance(item, dict) and item.get("roomName"):
                bound.add(str(item["roomName"]))
        return bound

    def sync(self, desired_rooms, mode="strict"):
        """同步本地配置与远程绑定状态。

        strict 模式确保服务端绑定与 desired_rooms 完全一致：
        绑定缺失的，解绑多余的。

        :return: dict 包含 bound, unbound, failed, unchanged 列表
        """
        desired_set = {str(r) for r in desired_rooms}
        self.logger.info("[RoomInfo.sync] 同步 %d 个房间，模式: %s",
                         len(desired_set), mode)

        bound_set = self.get_remote_bindings()

        if self.cookie_expired:
            return {"bound": [], "unbound": [], "failed": [], "unchanged": []}

        result = {"bound": [], "unbound": [], "failed": [], "unchanged": []}

        if mode == "strict":
            to_unbind = bound_set - desired_set
            to_bind = desired_set - bound_set
            matched = desired_set & bound_set
            result["unchanged"] = list(matched)

            for room in sorted(to_unbind):
                if self._unbind_room(room):
                    result["unbound"].append(room)
                else:
                    result["failed"].append((room, "unbind"))
                time.sleep(0.5)

            for room in sorted(to_bind):
                if self._bind_room(room):
                    result["bound"].append(room)
                else:
                    result["failed"].append((room, "bind"))
                time.sleep(0.5)

        self.logger.info("[RoomInfo.sync] 同步完成: 绑定 %d, 解绑 %d, 失败 %d, 未变 %d",
                         len(result["bound"]), len(result["unbound"]),
                         len(result["failed"]), len(result["unchanged"]))
        return result

    def is_cookie_expired(self):
        """返回 Cookie 是否已被检测为过期。"""
        return self.cookie_expired
