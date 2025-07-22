import sys
import time
import traceback
from utils import Defaults
from utils.Config import ConfigReader
from utils.RoomInfo import RoomInfo
from utils.NotificationManager import NotificationManager
from utils.Logger import get_logger


def main(path=None):
    # 初始化日志
    logger = get_logger()
    logger.info("UESTC-Energyfy 已启动...")

    # 初始化配置读取器
    if path:
        config_reader = ConfigReader(path)
    else:
        config_reader = ConfigReader()

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

            # 处理查询结果
            for room_name, result in results:
                if result is None:
                    continue

                balance = float(result.get("syje", '0.0'))
                logger.info(f"房间 {room_name} 当前余额: {balance:.2f}元")

                # 检查余额是否低于阈值
                if balance < alert_balance:
                    logger.info(f"房间 {room_name} 余额低于阈值 ({balance:.2f} < {alert_balance})")

                    # 查找该房间的配置
                    room_config = next((q for q in queries if q["room_name"] == room_name), None)
                    if not room_config:
                        continue

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
                                    short="快去交电费!!!"
                                )
                                logger.info(f"已向Server酱用户 {recipient['uid']} 发送通知")
                            except Exception as e:
                                logger.error(f"发送Server酱通知失败: {str(e)}")

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
                        logger.error(f"发送邮件失败: {str(e)}")

            # 处理检查间隔
            if check_interval <= 0:
                logger.info("单次检查模式，程序退出")
                return

            logger.info(f"下次检查将在 {check_interval} 秒后进行")
            time.sleep(check_interval)

        except Exception as e:
            # 处理配置验证失败
            if "validation" in str(e).lower():
                logger.error(f"配置文件验证失败: {str(e)}")
                logger.info("10秒后重试配置文件验证...")
                time.sleep(10)
            else:
                logger.error(f"主程序发生未处理异常: {str(e)}")
                logger.debug(traceback.format_exc())
                logger.info("30秒后重新启动...")
                time.sleep(30)


if __name__ == "__main__":
    # 存在参数时，使用第一个参数作为配置文件路径
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
