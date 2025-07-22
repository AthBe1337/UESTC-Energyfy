# UESTC-Energyfy

查询电子科技大学宿舍的电费余额，在低于阈值时发送邮件通知和Server酱推送。

## 通知示例

<img src="https://cloud.athbe.cn/f/Bef9/9USEFCXMK2QMH%602KP%28GX%7DTP.png" width="300" alt="邮件通知示例" />
<img src="https://cloud.athbe.cn/f/RNtB/578d16a600844487c70255a8e49b6911.jpg" width="300" alt="Server酱推送示例" />

## Server酱是什么？

*Server酱³专注于APP推送，大部分手机无需驻留后台亦可收信。*

前往[Server酱³ · 极简推送服务](https://sc3.ft07.com/)注册用户以获取`UUID`和`Sendkey`，在配置文件中启用Server酱并填写，在手机上安装应用即可接收推送。

## 快速开始

下载对应平台的Release版，解压并进入解压目录。

### 运行配置管理器

```bash
./ConfigManager Energyfy #若不加参数需要在启动后手动输入
```

**Windows中请以管理员身份运行**

启动后，会提示输入schema的路径，输入`./schema.json`即可。只有第一次启动需要这个操作。

进入主界面后，点击新建配置。跟据提示输入配置名，如`test`，不需要扩展名。

![](https://cloud.athbe.cn/f/dgiO/1J502MK3%7D@@C~%28R@Q$%5DFKX3.png)

点击确定，选中你刚刚创建的配置，点击编辑配置，进入编辑界面。

点击左侧菜单选择设置项，跟据右侧面板的描述，在下方编辑值。

![](https://cloud.athbe.cn/f/9wFp/QBI7J%5BMN__R%25%60%29LZT%7D0U%7B_N.png)

#### 注意

1. 查询间隔不要过短，否则账号可能会被冻结，建议至少在10分钟以上。
2. `queries`、`recipients`和`server_chan`中的`recipients`都是数组，你可以为其添加多个元素，即你可以一次查询多个宿舍，每个宿舍可设置多个收件人。
3. 每一项编辑完成后必须点击更新才能生效。
4. smtp相关设置请到你使用的邮箱官网查询。

编辑完成后，点击保存配置，保存成功后，点击激活配置。激活成功后，脚本默认会读取此配置。

### 运行脚本

```bash
./Energyfy #Windows中直接双击运行即可。
```

启动后，控制台默认会输出运行日志，同时在运行目录的`logs`目录下保存运行日志。

你可以使用`nohup`让脚本后台运行。

```bash
nohup ./Energyfy > /dev/null 2>&1 &
# 使用tail查看运行日志
tail -f logs/Energyfy.log
```

***你可以保存多份配置文件，并随时切换。脚本默认读取激活配置。***

## 常见问题

### 登录失败，状态码401

检查你的学号和密码是否正确，如果确定没有问题还是频繁出现401错误，可能是因为登录过于频繁，需要验证。你需要手动到官网登录，完成滑动验证。

### JS编译错误: Could not find an available JavaScript runtime ...

缺少`JavaScript`运行时，安装`npm`即可。

### Windows中使用配置管理器，创建符号链接失败

以管理员身份运行即可。

# 使用源码

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
python3 Energyfy.py ./config.json
```
