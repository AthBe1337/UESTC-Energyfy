# UESTC-Energyfy

查询电子科技大学宿舍的电费余额，在低于阈值时发送邮件通知和Server酱推送。

## 通知示例

<img src="https://cloud.athbe.cn/f/Bef9/9USEFCXMK2QMH%602KP%28GX%7DTP.png" width="300" />
<img src="https://cloud.athbe.cn/f/RNtB/578d16a600844487c70255a8e49b6911.jpg" width="300" />

## Server酱是什么？

*Server酱³专注于APP推送，大部分手机无需驻留后台亦可收信。*

前往[Server酱³ · 极简推送服务](https://sc3.ft07.com/)注册用户以获取`UUID`和`Sendkey`，在配置文件中启用Server酱并填写，并在手机上安装应用即可接收推送。

## 快速开始

脚本运行需要一个json配置文件，有两种方式获取。

### 1. ConfigManager

使用[AthBe1337/ConfigManager](https://github.com/AthBe1337/ConfigManager)对配置进行管理，支持多配置文件随时切换以及可视化的编辑。

如果你使用`git`克隆本仓库，你可以在`external`文件夹中找到它的源码，可以自行编译，也可以直接下载Release版使用。

#### 编译

```bash
#编译ConfigManager
git clone https://github.com/AthBe1337/UESTC-Energyfy.git
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
启动后，会提示输入schema的路径，schema位于仓库根目录，直接输入`../../../schema.json`即可。

进入主界面后，你可以对现有的配置文件进行编辑、删除、激活，也可以新建配置文件。只有激活的配置文件才会被读取。

![](https://cloud.athbe.cn/f/PVho/F%5BVMI4FNBOFR%5B9ZU%7BM~98G1.png)

可以在编辑界面对配置的每一项进行修改。右侧有详细信息。

![](https://cloud.athbe.cn/f/w3u6/_JIP5@6UUQ9LW%28T%2958H75MJ.png)

### 2. 手动编辑

如果你更习惯手动编辑，可以按照下面的模板手动编辑配置文件。

```json
{
  "username" : "",
  "password" : "",
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

当你编辑好配置文件后，可以开始运行`Energyfy.py`。

```bash
python3 Energyfy.py
```

如果你手动编辑配置文件，需要在启动时添加参数指定配置文件的目录。例如

```bash
python3 Energyfy.py ./config.json
```

日志将被保存于`log/Energyfy.log`。