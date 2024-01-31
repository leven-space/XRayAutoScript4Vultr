# XrayAutoScript4Vultr
XrayAutoScript4Vultr 是一个基于 [vultr-cli](https://github.com/vultr/vultr-cli) 封装的自动化 Shell 脚本项目。它旨在帮助用户在 Vultr 云服务平台上自动创建虚拟私服（VPS）实例，并安装 Xray 代理服务。脚本还提供了一个功能，可以将新创建的 VPS 实例的连接信息通过钉钉机器人自动发送到指定的钉钉群。

## 功能特性

- 自动化创建 Vultr VPS 实例
- 在新实例上自动部署 Xray 服务
- 将 VPS 连接信息发送至钉钉群
- 定期删除VPS 实例

## 系统要求

- 一个 Vultr 账户和相应的 API 密钥，配置好[VPS SSH KEY ](https://docs.vultr.com/deploy-a-new-server-with-an-ssh-key)
- 已安装 vultr-cli 并配置好 API 密钥
- Linux/Unix 环境 (包括 macOS) 或 WSL (Windows Subsystem for Linux)


## 安装与配置

1. 首先，确保你已经安装了 `vultr-cli` 并正确配置了 API 密钥。关于如何安装和配置 `vultr-cli` 的更多信息，请参阅其 [GitHub 页面](https://github.com/vultr/vultr-cli)。

2. 克隆或下载 AutoScript4Vultr 仓库：

```bash
git clone [https://github.com/yourusername/AutoScript4Vultr.git](https://github.com/leven-space/XRayAutoScript4Vultr)
cd XRayAutoScript4Vultr
```

3. 给予脚本执行权限：

```bash
chmod +x create-vultr-instance.sh
chmod +x install-vps.sh
chmod +x remove-vultr-instance.sh

```

4. 根据需要编辑脚本文件以配置 Xray 安装选项及其他设置。

5. 设置你的钉钉机器人 webhook URL，并将其添加到脚本中适当位置。详细步骤可参考[这里](https://ding-doc.dingtalk.com/doc#/serverapi2/qf2nxq)。

## 使用说明

按需运行 XRayAutoScript4Vultr 脚本来创建并设置你的 Vultr VPS 实例：

```bash
crontab -l

0 1 * * * /root/vultr/remove-vultr-instance.sh  >> /root/vultr/log_remove.log 2>&1
0 23 * * * /root/vultr/create-vultr-instance.sh >> /root/vultr/log_create.log 2>&1
10 23 * * * /root/vultr/install-vps.sh >> /root/vultr/log_install.log 2>&1
30 1 * * * /root/vultr/remove-vultr-instance.sh  >> /root/vultr/log_remove.log 2>&1
```

按照提示进行操作，完成后会收到包含新建 VPS 连接信息的消息推送至你设置好的钉钉群。

## 注意事项

使用此脚本之前，请确保你已经理解所有步骤并知晓如何处理可能出现的问题。该脚本会产生费用，因为它会在 Vultr 上创建付费资源。

请务必遵守相关法律法规和 Vultr 的使用政策，在使用 Xray 时不要从事任何违法活动。

## 贡献与支持

如果您有任何改进意见或遇到问题，请通过 GitHub Issue 提交您的反馈。

---

祝您使用愉快！
