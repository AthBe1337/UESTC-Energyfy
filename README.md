# UESTC-Energyfy

查询电子科技大学宿舍的电费余额，在低于阈值时发送邮件通知和*Server酱³*推送。

> Energyfy-NEXT已上线，无需复杂配置，注册账号即可使用！[立即访问](https://energyfy.top)

---

## 目录

- [通知示例](#通知示例)
- [Server酱³是什么？](#server酱是什么)
- [快速开始](#快速开始)
  - [运行配置管理器](#运行配置管理器)
  - [运行脚本](#运行脚本)
- [常见问题](#常见问题)
- [可选参数](#可选参数)
- [统计周报](#统计周报)
- [使用源码](#使用源码)
  - [1 ConfigManager](#1-configmanager)
  - [2 手动编辑](#2-手动编辑)

---

## 通知示例

| 邮件通知                                                     | Server酱推送                                                 |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| <img src="https://cloud.athbe.cn/f/Bef9/9USEFCXMK2QMH%602KP%28GX%7DTP.png" width="400" alt="邮件通知示例" /> | <img src="https://cloud.athbe.cn/f/RNtB/578d16a600844487c70255a8e49b6911.jpg" width="400" alt="Server酱推送示例" /> |

## Server酱³是什么？

> **Server酱³** 是一款专注于 APP 推送的服务，大部分手机无需后台常驻即可接收消息。

前往[Server酱³ · 极简推送服务](https://sc3.ft07.com/)注册用户以获取`UUID`和`Sendkey`，在配置文件中启用Server酱并填写，在手机上安装`Server酱`应用即可接收推送。

## 快速开始

前往 [Releases](https://github.com/AthBe1337/UESTC-Energyfy/releases) 下载对应平台的Release版，解压并进入解压目录。

### 运行配置管理器

为了方便在纯命令行环境(如ssh)下快速编辑配置，这里使用`TUI`配置管理器对配置进行编辑。

```bash
./ConfigManager Energyfy #若不加参数需要在启动后手动输入
```

>**Windows**中请以管理员身份运行

启动后，会提示输入schema的路径，输入`./schema.json`即可。只有第一次启动需要这个操作。

进入主界面后，点击新建配置。跟据提示输入配置名，如`test`，不需要扩展名。

![](https://cloud.athbe.cn/f/dgiO/1J502MK3%7D@@C~%28R@Q$%5DFKX3.png)

点击确定，选中你刚刚创建的配置，点击编辑配置，进入编辑界面。

点击左侧菜单选择设置项，跟据右侧面板的描述，在下方编辑值。

![](https://cloud.athbe.cn/f/9wFp/QBI7J%5BMN__R%25%60%29LZT%7D0U%7B_N.png)

#### 注意

1. 查询间隔不要过短，否则账号可能会被冻结，建议至少在10分钟以上。
2. `queries`、`recipients`和`server_chan`中的`recipients`都是数组，你可以为其添加多个元素，即可一次查询多个宿舍并推送给多人。
3. 每一项编辑完成后必须点击更新才能生效。
4. smtp相关设置请到你使用的邮箱官网查询。

编辑完成后，点击保存配置，保存成功后，点击激活配置。激活成功后，脚本默认会读取此配置。

### 运行脚本

```bash
./Energyfy #Windows中直接双击运行即可。
```

启动后，控制台默认会输出运行日志，同时在运行目录的`logs/`目录下保存运行日志。

你可以使用`nohup`让脚本后台运行。

```bash
nohup ./Energyfy --no-log-to-console > /dev/null 2>&1 &
# 使用tail查看运行日志
tail -f logs/Energyfy.log
```

>***你可以保存多份配置文件，并随时切换。脚本默认读取激活配置。***

## 升级注意事项（v1.3.1）

v1.3.1 修复了浏览器指纹随机性问题。**所有 v1.3.0 用户建议升级**，旧版本生成的 BFP 为所有用户共享值，存在安全隐患。

升级后需要**重新执行** `--verify` 以生成唯一的浏览器指纹：

```bash
python Energyfy.py --verify
```

如需在多台机器间共享同一指纹（如 Docker 部署迁移），可使用 `--seed` 指定种子：

```bash
python Energyfy.py --verify --seed my-device
```

## 升级注意事项（v1.3.0）

v1.3.0 适配了统一认证平台新增的**浏览器指纹二次认证**机制。老用户升级后需完成以下步骤：

### 1. 更新 Schema

如果你使用默认配置路径，需要手动更新 `~/.config/Energyfy/schema.json`，在 `"password"` 字段后添加：

```json
"bfp": {
  "type": "string",
  "description": "浏览器指纹，运行 --verify 后自动生成并持久化，用于跳过二次认证。"
},
```

### 2. 完成首次验证

```bash
python Energyfy.py --verify
# 或使用 Release 版：
./Energyfy --verify
```

根据提示输入短信验证码，完成后 bfp 会自动写入配置文件。后续运行时将跳过二次认证。

### 3. 配置模板（手动编辑）

```json
{
  "username" : "",
  "password" : "",
  "bfp": "",
  ...
}
```

### 4. 环境变量

新增 `UESTC_BFP` 环境变量，可用于传递浏览器指纹：

```bash
UESTC_BFP="xxx" python Energyfy.py -c config.json
```

### 5. 第三方库调用

如果其他项目引用了 `RoomInfo`，可通过 `bfp` 参数传入指纹，通过 `verify_code_handler` 回调处理验证码：

```python
from utils.RoomInfo import RoomInfo, TwoFactorRequired

def get_code(msg):
    return input(f"{msg}\n请输入验证码: ").strip()

room_info = RoomInfo(username, password, bfp=loaded_bfp, verify_code_handler=get_code)
try:
    result = room_info.get(["121604"])
except TwoFactorRequired:
    # 没有设置 verify_code_handler 时抛出，提示用户运行 --verify
    print("需要二次认证")
```

## 常见问题

### 登录失败，状态码401

检查你的学号和密码是否正确。如果确认无误仍频繁出现401，可能是因为登录过于频繁导致IP被冻结，需要等待一段时间后重试。

### 需要二次认证

如果运行时报错 `需要二次认证`，说明浏览器指纹未设置或已过期。运行以下命令完成验证：

```bash
python Energyfy.py --verify
```

验证成功后 bfp 会自动保存，之后即可正常使用。

### JS编译错误: Could not find an available JavaScript runtime ...

缺少`JavaScript`运行时，安装`npm`即可。

### Windows中使用配置管理器，创建符号链接失败

以管理员身份运行即可。

## 可选参数

- `-h` `--help` 显示帮助信息
- `-c` `--config` 指定配置文件路径
- `-v` `--version` 显示版本信息
- `-l` `--log-level` 设置日志等级`(DEBUG|INFO|WARNING|ERROR|CRITICAL)`，默认为`INFO`
- `--no-log-to-console` 禁用控制台输出日志
- `--no-log-to-file` 禁用文件输出日志
- `-f` `--log-file` 指定日志文件路径，默认为`logs/Energyfy.log`
- `-b` `--backup-count` 指定日志文件备份数量，默认为`7`
- `--report-interval` 统计电费消耗的周期，单位为天，默认为0，代表不统计。
- `--verify` 交互式验证模式，完成登录和短信验证码认证后将浏览器指纹持久化到配置文件。首次使用或指纹失效时需要运行。
- `--seed` 指定 BFP 种子字符串，与 `--verify` 配合使用。同一 seed 可跨机器生成相同的浏览器指纹；不提供则每次随机生成，保证指纹唯一。

### 环境变量

如果你不想将统一认证用户名与密码持久保存在配置文件中，可以在运行脚本前用以下环境变量指定，配置文件中相应项留空即可。

- `UESTC_USERNAME` 统一认证用户名
- `UESTC_PASSWORD` 统一认证密码
- `UESTC_BFP` 浏览器指纹，用于跳过二次认证

**示例用法**
```bash
./Energyfy -c config.json #使用./config.json作为配置文件
./Energyfy -l DEBUG -f logs/Energyfy.log #使用DEBUG级别日志，将日志输出到logs/Energyfy.log
./Energyfy -b 10 #指定日志文件备份数量为10
```

## 统计周报

现在可以在指定的周期后统计电费消耗趋势，并发送图表到收件人邮箱。示例如下。

<img src="https://cloud.athbe.cn/f/WdEfm/I5KHP%29HHHICXY9QQQ6@%254%5BH.png" width="400" alt="用电报告示例" />

### 兼容性
完全兼容旧版本配置文件，由于新增了绘图功能，脚本资源开销会稍微增加。如果服务器资源过于紧张，可以选择不升级。

### 开启方式
如果你使用linux系统，首先保证安装中文字体
```bash
# Debian/Ubuntu/Kali
sudo apt-get install -y fonts-wqy-microhei
# ArchLinux
sudo pacman -S wqy-microhei
# Fedora/CentOS/RHEL
sudo yum install -y wqy-microhei
```
启动时添加参数`--report-interval n`
其中n为统计周期，单位为天，默认为0，代表不统计。

## 使用源码

脚本运行需要一个json配置文件，有两种方式获取。

### 1. ConfigManager

使用[AthBe1337/ConfigManager](https://github.com/AthBe1337/ConfigManager)对配置进行管理，支持多配置文件随时切换以及可视化的编辑。

如果你使用`git`克隆本仓库，你可以在`external`文件夹中找到它的源码，可以自行编译，也可以直接下载Release版使用。

#### 编译

```bash
#编译ConfigManager
git clone --recurse-submodules https://github.com/AthBe1337/UESTC-Energyfy.git
cd UESTC-Energyfy/external/ConfigManager
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

#Windows下可以使用Ninja
#cmake .. -G "Ninja" -DCMAKE_BUILD_TYPE=Release
#ninja -j18

#运行ConfigManager
./ConfigManager Energyfy
```

### 2. 手动编辑

如果你更习惯手动编辑，可以按照下面的模板手动编辑配置文件。

```json
{
  "username" : "",
  "password" : "",
  "bfp": "",
  "check_interval": 600,
  "alert_balance" : 10,
  "smtp": {
    "server": "",
    "port": 465,
    "username": "",
    "password": "",
    "security": ""
  },
  "queries" : [
    {
      "room_name": "",
      "recipients": [
        ""
      ],
      "server_chan": {
        "enabled": true,
        "recipients" : [
          {
            "uid": "",
            "sendkey": ""
          }
        ]
      }
    }
  ]
}
```

如果使用手动编辑的配置文件，在启动脚本时应该添加参数以指定配置文件路径。

```bash
python3 Energyfy.py -c ./config.json
```