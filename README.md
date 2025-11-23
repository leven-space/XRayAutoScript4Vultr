# XrayAutoScript4Vultr
XrayAutoScript4Vultr 是一个基于 [vultr-cli](https://github.com/vultr/vultr-cli) 封装的自动化 Shell 脚本项目。它旨在帮助用户在 Vultr 云服务平台上自动创建虚拟私服（VPS）实例，并安装 Xray 代理服务。脚本还提供了一个功能，可以将新创建的 VPS 实例的连接信息通过钉钉机器人自动发送到指定的钉钉群。

## 功能特性

- 自动化创建 Vultr VPS 实例
- 在新实例上自动部署 Xray 服务
- **一键创建**：创建VPS后自动等待实例就绪并安装Xray
- 将 VPS 连接信息发送至钉钉群
- 定期删除VPS 实例
- Web管理面板支持
- **Web管理面板**：提供友好的Web界面进行VPS管理
- **API接口**：支持通过HTTP API远程管理VPS
- **多地区支持**：支持32个Vultr数据中心地区
- **灵活配置**：支持自定义Xray协议类型（Reality/TCP）
- **自动重装**：支持Xray服务的重新安装和配置

## 系统要求

- 一个 Vultr 账户和相应的 API 密钥，配置好[VPS SSH KEY ](https://docs.vultr.com/deploy-a-new-server-with-an-ssh-key)
- 已安装 vultr-cli 并配置好 API 密钥
- Linux/Unix 环境 (包括 macOS) 或 WSL (Windows Subsystem for Linux)
- Python 3.x（用于Web管理面板）
- Flask框架：`pip install flask`

## 安装与配置

### 1. 环境准备

首先，确保你已经安装了 `vultr-cli` 并正确配置了 API 密钥。关于如何安装和配置 `vultr-cli` 的更多信息，请参阅其 [GitHub 页面](https://github.com/vultr/vultr-cli)。

### 2. 项目部署

克隆或下载 AutoScript4Vultr 仓库：

```bash
git clone https://github.com/leven-space/XRayAutoScript4Vultr.git
cd XRayAutoScript4Vultr
```

### 3. 权限设置

给予脚本执行权限：

```bash
chmod +x create-vultr-instance.sh
chmod +x install-vps.sh
chmod +x remove-vultr-instance.sh
```

### 4. 配置文件

编辑 `conf.env` 文件，配置以下参数：

```bash
# Vultr API配置
VULTR_API_KEY="你的Vultr API密钥"
VULTR_CLI="/root/vultr/vultr-cli"  # vultr-cli的路径

# VPS配置
VULTR_INSTANCE_PLAN="vc2-1c-1gb"    # VPS套餐类型
VULTR_INSTANCE_OS_ID="2136"         # 操作系统ID（Ubuntu 22.04）
VULTR_INSTANCE_REGION="nrt"         # 默认地区（东京）

# SSH配置
SSH_KEY_PATH="/root/.ssh/id_rsa"    # SSH私钥路径
SSH_KEY_ID="你的SSH密钥ID"          # Vultr上的SSH密钥ID

# 通知配置
DINGTALK_NOTICE_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=你的钉钉机器人Token"
```

### 5. 钉钉机器人配置

设置你的钉钉机器人 webhook URL，并将其添加到 `conf.env` 文件中。详细步骤可参考[钉钉官方文档](https://ding-doc.dingtalk.com/doc#/serverapi2/qf2nxq)。

## 使用说明

### 方法1：命令行使用

按需运行 XRayAutoScript4Vultr 脚本来创建并设置你的 Vultr VPS 实例：

```bash
# 创建并配置VPS（包含Xray安装）
./create-vultr-instance.sh [--region 地区代码] [--xrayschema tcp|reality]

# 仅安装/重装Xray
./install-vps.sh [--xrayschema tcp|reality]

# 删除所有VPS实例
./remove-vultr-instance.sh
```

### 方法2：Web管理面板

启动Web管理面板：

```bash
python dashboard_server.py
```

访问 `http://localhost:5000` 即可使用Web界面管理VPS。

Web面板功能：
- **创建VPS**：仅创建Vultr实例（传统方式）
- **一键创建**：创建VPS实例并自动安装Xray（推荐）
- **删除所有VPS**：一键清理所有实例
- **重装Xray**：选择协议类型（Reality/TCP）进行重装
- **实时日志**：查看操作执行结果
- **状态监控**：查看后台任务执行状态

### 方法3：API接口

项目提供RESTful API接口，支持远程管理：

#### 创建VPS
```bash
POST /vps/create
Content-Type: application/json

{
    "password": "112233@leven",
    "region": "nrt",
    "duration": 55
}
```

#### 删除所有VPS
```bash
POST /vps/remove
Content-Type: application/json

{
    "password": "112233@leven"
}
```

#### 重装Xray
```bash
POST /vps/xray
Content-Type: application/json

{
    "password": "112233@leven",
    "xrayschema": "reality"
}
```

### 方法4：定时任务

使用crontab设置定时任务：

```bash
# 编辑crontab
crontab -e

# 添加以下任务
0 1 * * * /root/vultr/remove-vultr-instance.sh  >> /root/vultr/log_remove.log 2>&1
0 23 * * * /root/vultr/create-vultr-instance.sh >> /root/vultr/log_create.log 2>&1
10 23 * * * /root/vultr/install-vps.sh >> /root/vultr/log_install.log 2>&1
30 1 * * * /root/vultr/remove-vultr-instance.sh  >> /root/vultr/log_remove.log 2>&1
```

## 支持地区

项目支持32个Vultr数据中心地区，包括：

| 地区代码 | 城市 | 国家 |
|---------|------|------|
| nrt | 东京 | 日本 |
| sgp | 新加坡 | 新加坡 |
| bom | 孟买 | 印度 |
| icn | 首尔 | 韩国 |
| lax | 洛杉矶 | 美国 |
| sjc | 硅谷 | 美国 |
| ... | ... | ... |

完整地区列表请查看 `regions_list.txt` 文件。

## 注意事项

使用此脚本之前，请确保你已经理解所有步骤并知晓如何处理可能出现的问题。该脚本会产生费用，因为它会在 Vultr 上创建付费资源。

### 费用提醒
- VPS实例按小时计费
- 建议设置合理的运行时长，避免不必要的费用
- 使用删除功能及时清理不再需要的实例

### 安全建议
- 妥善保管API密钥和SSH私钥
- 定期更换钉钉机器人Webhook地址
- 不要在公共环境暴露管理密码

### 故障排查
- 检查 `conf.env` 文件配置是否正确
- 确认Vultr账户余额充足
- 查看日志文件了解详细错误信息
- 确保SSH密钥已正确添加到Vultr账户

请务必遵守相关法律法规和 Vultr 的使用政策，在使用 Xray 时不要从事任何违法活动。

## 贡献与支持

如果您有任何改进意见或遇到问题，请通过 GitHub Issue 提交您的反馈。

---

祝您使用愉快！
