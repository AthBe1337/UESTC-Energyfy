import threading
import time
import re
import os
import io
import json
import datetime
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from utils import Defaults
from utils.Logger import get_logger
from utils.NotificationManager import NotificationManager


class StatisticsReporter(threading.Thread):
    def __init__(self, config_reader, log_file_path, interval_days):
        """
        :param config_path: 配置文件路径 (用于热重载)
        :param notification_manager: 通知管理器实例
        :param log_file_path: 日志文件路径
        :param interval_days: 统计周期
        """
        super().__init__()
        self.config_reader = config_reader  # 保存路径而不是对象
        self.log_path = log_file_path
        self.interval = interval_days
        self.daemon = True
        self.logger = get_logger()

        # 状态文件保存位置 (与日志同目录)
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except:
                pass
        self.state_file = os.path.join(log_dir if log_dir else '.', "stats_state.json")

    def _load_state(self):
        """读取上次统计时间"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_state(self, state):
        """保存统计时间"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            self.logger.error(f"无法保存统计状态: {e}")

    def _collect_logs(self, days):
        """收集过去 N 天的所有日志行"""
        lines = []
        now = datetime.datetime.now()
        start_time = now - datetime.timedelta(days=days)
        base_name = os.path.basename(self.log_path)
        dir_name = os.path.dirname(self.log_path)
        target_files = []
        if os.path.exists(self.log_path):
            target_files.append(self.log_path)
        if os.path.exists(dir_name):
            for file in os.listdir(dir_name):
                if file.startswith(base_name + "."):
                    target_files.append(os.path.join(dir_name, file))

        for fp in target_files:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    lines.extend(f.readlines())
            except Exception as e:
                self.logger.warning(f"无法读取日志文件 {fp}: {e}")
        return lines

    def _parse_data(self, lines, room_name, days):
        """从日志行中提取 (datetime, balance)"""
        data = []
        now = datetime.datetime.now()
        start_time = now - datetime.timedelta(days=days)
        safe_room_name = str(room_name)

        # 修正后的正则，移除行首锚点，放宽匹配
        pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}).*?房间\s+' +
            re.escape(safe_room_name) +
            r'.*?当前余额:\s*([\d\.]+)'
        )

        for line in lines:
            match = pattern.search(line)
            if match:
                dt_str, bal_str = match.groups()
                try:
                    dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    if dt >= start_time:
                        data.append((dt, float(bal_str)))
                except ValueError:
                    continue
        data.sort(key=lambda x: x[0])
        return data

    def _draw_chart(self, room_name, data):
        """绘制图表并返回 bytes"""
        if not data:
            return None
        dates = [x[0] for x in data]
        values = [x[1] for x in data]
        plt.figure(figsize=(10, 5), dpi=100)
        # 中文字体兜底
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False

        plt.plot(dates, values, label='余额', color='#3498db', linewidth=2, marker='.', markersize=8)
        plt.fill_between(dates, values, alpha=0.1, color='#3498db')
        plt.title(f"宿舍 {room_name} 电费余额趋势", fontsize=14)
        plt.xlabel("时间")
        plt.ylabel("余额 (元)")
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %Hh'))
        plt.gcf().autofmt_xdate()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close()
        return buf.getvalue()

    def _calculate_stats(self, data):
        """
        根据解析的数据计算统计指标
        :param data: list of (datetime, balance)
        :return: dict
        """
        if not data or len(data) < 2:
            return None

        # 1. 基础数据
        start_time, start_bal = data[0]
        end_time, end_bal = data[-1]

        # 2. 计算消耗 (注意：如果期间充值了，直接减可能会出现负数，这里简单处理为净支出)
        net_cost = start_bal - end_bal

        # 3. 计算时间跨度 (天)
        time_span_days = (end_time - start_time).total_seconds() / (24 * 3600)
        if time_span_days < 0.1:
            time_span_days = 0.1  # 防止除以零

        # 4. 计算日均
        # 如果 net_cost 是负数（充值了），日均消耗就没有意义了，记为 0
        if net_cost > 0:
            daily_avg = net_cost / time_span_days
        else:
            daily_avg = 0.0

        # 5. 预测剩余天数
        days_left = "∞"
        if daily_avg > 0 and end_bal > 0:
            left_val = end_bal / daily_avg
            if left_val < 999:
                days_left = str(int(left_val))

        return {
            "start_bal": f"{start_bal:.2f}",
            "end_bal": f"{end_bal:.2f}",
            "cost": f"{net_cost:.2f}" if net_cost > 0 else f"+{abs(net_cost):.2f} (充值)",
            "daily_avg": f"{daily_avg:.2f}",
            "days_left": days_left
        }

    def run(self):
        if self.interval <= 0:
            self.logger.info("统计报告服务已禁用")
            return

        self.logger.info(f"统计报告服务已启动 (周期: {self.interval}天)")

        while True:
            try:
                try:
                    queries = self.config_reader.get("queries")
                except Exception as e:
                    self.logger.error(f"读取配置文件失败，跳过本次统计: {e}")
                    time.sleep(60)  # 配置出错时缩短等待时间以便快速恢复
                    continue

                smtp_config = self.config_reader.get("smtp")
                if smtp_config:
                    notification = NotificationManager(
                        email_host=smtp_config["server"],
                        email_port=smtp_config["port"],
                        encryption=smtp_config["security"],
                        email_username=smtp_config["username"],
                        email_password=smtp_config["password"],
                        email_sender=smtp_config["username"]
                    )
                else:
                    self.logger.error("未找到SMTP配置")
                    time.sleep(60)
                    continue
                state = self._load_state()
                now_ts = time.time()
                day_seconds = 24 * 3600

                logs_cache = None

                for query in queries:
                    room = query['room_name']
                    recipients = query['recipients']

                    last_report = state.get(str(room), 0)

                    if (now_ts - last_report) > (self.interval * day_seconds):
                        self.logger.info(f"正在为 {room} 生成统计报告...")

                        if logs_cache is None:
                            logs_cache = self._collect_logs(self.interval)

                        room_data = self._parse_data(logs_cache, room, self.interval)

                        if len(room_data) < 2:
                            self.logger.warning(f"{room} 数据不足(少于2个点)，跳过")
                            continue

                        stats = self._calculate_stats(room_data)
                        if not stats:
                            self.logger.warning(f"{room} 无法计算统计数据")
                            continue

                        img_bytes = self._draw_chart(room, room_data)
                        if img_bytes:
                            cid = "chart_img"

                            html = Defaults.generate_report_email(room, self.interval, cid, stats)

                            text = (f"宿舍 {room} 电费周报\n"
                                    f"期间支出: {stats['cost']}元\n"
                                    f"当前余额: {stats['end_bal']}元\n"
                                    f"日均消费: {stats['daily_avg']}元/天\n"
                                    f"预计可用: {stats['days_left']}天\n"
                                    f"请查看邮件HTML内容获取趋势图。")

                            notification.send_email(
                                recipients=recipients,
                                subject=f"[{room}] 电费统计报告 - 余额{stats['end_bal']}元",
                                text_content=text,
                                html_content=html,
                                images={cid: img_bytes}
                            )

                            state[str(room)] = now_ts
                            self._save_state(state)
                            self.logger.info(f"{room} 统计报告发送成功")

                time.sleep(3600)

            except Exception as e:
                self.logger.exception("统计线程发生异常")
                time.sleep(3600)