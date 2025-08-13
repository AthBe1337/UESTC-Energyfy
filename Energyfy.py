import sys
import time
import argparse
import os
import concurrent.futures
from utils import Defaults
from utils.Config import ConfigReader
from utils.RoomInfo import RoomInfo
from utils.NotificationManager import NotificationManager
from utils.Logger import get_logger


def parse_args():
    parser = argparse.ArgumentParser(
        description="UESTC-Energyfy 电子科大宿舍电费余额告警服务"
    )

    def abs_path(path_str):
        """将路径转换为绝对路径并展开用户目录"""
        if path_str is None:
            return None
        return os.path.abspath(os.path.expanduser(path_str))

    parser.add_argument(
        "-c", "--config",
        help="指定配置文件路径",
        type=abs_path,   # 自动解析路径
        default=None
    )
    parser.add_argument(
        "-l", "--log-level",
        help="日志等级（DEBUG/INFO/WARNING/ERROR/CRITICAL），默认为INFO",
        type=str.upper,  # 自动转大写
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    )

    # 双向布尔参数 - 控制台日志
    log_console_group = parser.add_mutually_exclusive_group()
    log_console_group.add_argument(
        "--log-to-console",
        dest="log_to_console",
        action="store_true",
        help="启用日志输出到控制台（默认开启）"
    )
    log_console_group.add_argument(
        "--no-log-to-console",
        dest="log_to_console",
        action="store_false",
        help="禁用日志输出到控制台"
    )
    parser.set_defaults(log_to_console=True)

    # 双向布尔参数 - 文件日志
    log_file_group = parser.add_mutually_exclusive_group()
    log_file_group.add_argument(
        "--log-to-file",
        dest="log_to_file",
        action="store_true",
        help="启用日志输出到文件（默认开启）"
    )
    log_file_group.add_argument(
        "--no-log-to-file",
        dest="log_to_file",
        action="store_false",
        help="禁用日志输出到文件"
    )
    parser.set_defaults(log_to_file=True)

    parser.add_argument(
        "-f", "--log-file",
        help="日志文件路径",
        type=abs_path,  # 日志文件路径也支持绝对化
        default=abs_path("logs/Energyfy.log")
    )
    parser.add_argument(
        "-b", "--backup-count",
        help="日志备份数量",
        type=int,
        default=7
    )

    return parser.parse_args()

def send_notifications(room_name, balance, alert_balance, room_config, notification):
    """并行发送通知的辅助函数"""
    logger = get_logger()

    # 准备通知内容
    text_content = Defaults.generate_text_email(room_name, balance, alert_balance)
    html_content = Defaults.generate_html_email(room_name, balance, alert_balance)
    markdown_content = Defaults.generate_markdown_notification(room_name, balance, alert_balance)

    # 发送Server酱通知
    if room_config["server_chan"]["enabled"]:
        for recipient in room_config["server_chan"]["recipients"]:
            try:
                notification.send_server_chan(
                    uid=recipient["uid"],
                    sendkey=recipient["sendkey"],
                    title="电费余额告警",
                    desp=markdown_content,
                    short="宿舍电费余额不足，请尽快缴费!",
                )
                logger.info(f"已向Server酱用户 {recipient['uid']} 发送通知")
            except Exception as e:
                logger.exception(f"发送Server酱通知失败（用户 {recipient['uid']}）")

    # 发送邮件通知
    try:
        notification.send_email(
            recipients=room_config["recipients"],
            subject=f"电费余额告警 - {room_name}",
            text_content=text_content,
            html_content=html_content
        )
        logger.info(f"已向房间 {room_name} 发送邮件通知")
    except Exception as e:
        logger.exception(f"发送邮件失败（房间 {room_name}）")


def main(path=None):
    # 初始化日志
    logger = get_logger()
    logger.info("UESTC-Energyfy 已启动...")

    # 初始化配置读取器
    while True:
        try:
            config_reader = ConfigReader(path)
            break
        except Exception as e:
            logger.exception("配置文件验证失败")
            logger.info("30秒后重试配置文件验证...")
            time.sleep(30)

    # 主循环
    while True:
        try:

            logger.info("===============开始查询===============")

            # 验证配置文件
            config_reader.validate()
            logger.info("配置文件验证通过")
            logger.info("当前配置:")
            for line in str(config_reader).split("\n"):
                logger.info(line)

            # 读取配置
            username = config_reader.get("username")
            password = config_reader.get("password")
            check_interval = config_reader.get("check_interval")
            alert_balance = config_reader.get("alert_balance")
            smtp_config = config_reader.get("smtp")
            queries = config_reader.get("queries")

            # 初始化通知管理器
            notification = NotificationManager(
                email_host=smtp_config["server"],
                email_port=smtp_config["port"],
                encryption=smtp_config["security"],
                email_username=smtp_config["username"],
                email_password=smtp_config["password"],
                email_sender=smtp_config["username"]
            )

            # 初始化房间信息查询器
            room_info = RoomInfo(username, password)

            # 获取所有房间名称
            room_names = [q["room_name"] for q in queries]

            # 查询房间余额
            logger.info(f"开始查询{len(room_names)}个房间的余额信息")
            results = room_info.get(room_names)

            # 处理需要通知的房间
            alert_rooms = []
            for room_name, result in results:
                if result is None:
                    logger.warning(f"房间 {room_name} 查询失败")
                    continue

                balance = float(result.get("syje", '0.0'))

                # 检查余额是否低于阈值
                if balance < alert_balance:
                    logger.info(f"房间 {room_name} 当前余额: {balance:.2f}元, 低于阈值 ({balance:.2f} < {alert_balance})")
                    alert_rooms.append((room_name, balance))
                else:
                    logger.info(f"房间 {room_name} 当前余额: {balance:.2f}元")

            # 并行发送通知
            if alert_rooms:
                logger.info(f"{len(alert_rooms)}个房间需要通知")

                # 使用线程池并行发送
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for room_name, balance in alert_rooms:
                        # 查找该房间的配置
                        room_config = next((q for q in queries if q["room_name"] == room_name), None)
                        if not room_config:
                            continue

                        # 提交发送任务
                        future = executor.submit(
                            send_notifications,
                            room_name, balance, alert_balance, room_config, notification
                        )
                        futures.append(future)

                    # 等待所有任务完成
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            logger.exception("通知任务异常")

            # 处理检查间隔
            if check_interval <= 0:
                logger.info("单次检查模式，程序退出")
                return

            logger.info(f"下次检查将在 {check_interval} 秒后进行")
            time.sleep(check_interval)

        except Exception as e:
            logger.exception("主程序发生未处理异常")
            logger.info("30秒后重新启动...")
            time.sleep(30)


if __name__ == "__main__":
    args = parse_args()
    get_logger(
        name="Energyfy",
        log_level=getattr(sys.modules["logging"], args.log_level),
        log_to_console=args.log_to_console,
        log_to_file=args.log_to_file,
        log_file=args.log_file,
        backup_count=args.backup_count
    )
    main(args.config)