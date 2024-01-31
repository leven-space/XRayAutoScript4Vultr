#!/bin/bash

# --------------------------------------------------
# Vultr API KEY
export VULTR_API_KEY="your vultr api key"

# Vultr CLI 命令路径（如果已经在环境变量中，直接使用 vultr-cli 即可）
VULTR_CLI="/root/vultr/vultr-cli"
HOME_PATH="your script dir path"

# Vultr SSH 私钥文件路径,默认为/root/.ssh/id_rsa
SSH_KEY_PATH="your ssh path"

# 创建Vultr实例的参数
REGION="nrt"
PLAN="vc2-1c-1gb"
OS_ID="2136"
SSH_KEY_ID="your vultr ssh key id"

# 钉钉 webhook_url
WEBHOOK_URL= "your dingding url"

# --------------------------------------------------


# 创建临时文件用于存储输出信息
OUTPUT_FILE=$(mktemp)


# DingDing 通知
send_dingtalk_message() {
    local message=$1
    local webhook_url=$WEBHOOK_URL
    # 发送POST请求
    curl "$webhook_url" \
        -H 'Content-Type: application/json' \
        -d "{
            \"msgtype\": \"text\",
            \"text\": {
                \"content\": \"$message\"
            }
        }"
}

# 首先调用 remove-vultr-instance.sh 脚本来删除现有实例,注意需要配置
sh $HOME_PATH/remove-vultr-instance.sh

# 检查上一个命令是否成功执行
if [ $? -ne 0 ]; then
    echo "Failed to remove existing instances. Exiting..." | tee -a "$OUTPUT_FILE"
    exit 1
fi


# 创建实例并获取ID
echo "Creating Vultr instance..."
CREATE_OUTPUT=$($VULTR_CLI instance create --region $REGION --plan $PLAN --os $OS_ID --ssh-keys $SSH_KEY_ID)

if [[ $? -ne 0 ]]; then
    echo "Failed to create Vultr instance." | tee -a "$OUTPUT_FILE"
    exit 1
fi

INSTANCE_ID=$(echo "$CREATE_OUTPUT" | grep 'ID' | awk '{print $2}')

if [[ -z "$INSTANCE_ID" ]]; then
    echo "Unable to find Instance ID from creation output." | tee -a "$OUTPUT_FILE"
    exit 1
fi

echo "Instance created with ID: $INSTANCE_ID" | tee -a "$OUTPUT_FILE"

# 循环检查实例状态直到它包含 active 并获取MAIN IP地址
while true; do
    echo "Checking instance status..."
    INSTANCE_INFO=$($VULTR_CLI instance get $INSTANCE_ID)

    STATUS=$(echo "$INSTANCE_INFO" | grep -io 'STATUS\s\+active') # 使用正则表达式匹配 STATUS 和 active

    if [[ $STATUS ]]; then # 检查是否有匹配
        # 使用 awk 正则表达式来匹配 MAIN IP 后跟随的IP地址
        MAIN_IP=$(echo "$INSTANCE_INFO" | awk '/MAIN IP/ {for(i=1;i<=NF;i++) if ($i=="IP") print $(i+1)}')
        break # 跳出循环当状态包含 active
    else
        echo "Instance is not active yet. Waiting for 30 seconds..."
        sleep 30 # 等待30秒再次检查状态
    fi
done

echo "Instance is active with MAIN IP: $MAIN_IP" | tee -a "$OUTPUT_FILE"

echo "Waiting for 1 minute before logging in..."
sleep 120

# SSH 登陆到主机并禁用UFW防火墙 (确保你有权限无密码登陆)
echo "Disabling UFW firewall on the server..."
ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP << EOF
ufw disable
EOF

if [[ $? -eq 0 ]]; then
    echo "UFW firewall has been disabled successfully." | tee -a "$OUTPUT_FILE"
else
    echo "Failed to disable UFW firewall." | tee -a "$OUTPUT_FILE"
fi

echo "Running install xray script from GitHub..." | tee -a "$OUTPUT_FILE"
INSTALL_OUTPUT=$(ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'bash <(wget -qO- -o- https://github.com/233boy/Xray/raw/main/install.sh)')

echo "$INSTALL_OUTPUT" | tee -a "$OUTPUT_FILE"

# 将临时文件内容读取到变量中，并发送通知消息至钉钉群组机器人
MESSAGE_CONTENT=$(<"$OUTPUT_FILE")
send_dingtalk_message "$MESSAGE_CONTENT"

# 清理：删除临时文件
rm "$OUTPUT_FILE"

exit 0 # 脚本执行成功结束退出码为0.
