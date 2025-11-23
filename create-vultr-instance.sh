#!/bin/bash

# 导入配置文件
source ./conf.env

# 创建临时文件用于存储输出信息
OUTPUT_FILE=$(mktemp)

# 默认值
region=$VULTR_INSTANCE_REGION
xrayschema=reality

# 解析命令行选项和参数
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --region) region="$2"; shift ;;
        --xrayschema) xrayschema="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift # 移动到下一个键值对
done


# DingDing 通知
send_dingtalk_message() {
    local message=$1
    # 发送POST请求
    curl "$DINGTALK_NOTICE_WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{
            \"msgtype\": \"text\",
            \"text\": {
                \"content\": \"$message\"
            }
        }"
}

# 确保脚本结束前发送通知
send_notification_before_exit() {
    # 将临时文件内容读取到变量中，并发送通知消息至钉钉群组机器人
    MESSAGE_CONTENT=$(<"$OUTPUT_FILE")
    send_dingtalk_message "$MESSAGE_CONTENT"
    
    # 清理：删除临时文件
    rm "$OUTPUT_FILE"
    exit ${1:-0} # 默认成功退出，但可以传递自定义退出码
}

# 设置退出陷阱，确保无论如何都发送通知
trap 'send_notification_before_exit $?' EXIT INT TERM

# 首先调用 remove-vultr-instance.sh 脚本来删除现有实例
sh ./remove-vultr-instance.sh

# 检查上一个命令是否成功执行
if [ $? -ne 0 ]; then
    echo "Failed to remove existing instances. Exiting..." | tee -a "$OUTPUT_FILE"
    exit 1
fi



# 创建实例并获取ID
echo "Creating Vultr instance..."
CREATE_OUTPUT=$($VULTR_CLI instance create --region $region --plan $VULTR_INSTANCE_PLAN --os $VULTR_INSTANCE_OS_ID --ssh-keys $SSH_KEY_ID)

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
MAX_WAIT_TIME=600 # 10分钟最大等待时间
START_TIME=$(date +%s)
while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED_TIME=$((CURRENT_TIME - START_TIME))
    
    if [[ $ELAPSED_TIME -gt $MAX_WAIT_TIME ]]; then
        echo "Timeout waiting for instance to become active after $((MAX_WAIT_TIME/60)) minutes." | tee -a "$OUTPUT_FILE"
        exit 1
    fi
    
    echo "Checking instance status..."
    INSTANCE_INFO=$($VULTR_CLI instance get $INSTANCE_ID)

    STATUS=$(echo "$INSTANCE_INFO" | grep -io 'STATUS\s\+active') # 使用正则表达式匹配 STATUS 和 active

    if [[ $STATUS ]]; then # 检查是否有匹配
        # 使用 awk 正则表达式来匹配 MAIN IP 后跟随的IP地址
        MAIN_IP=$(echo "$INSTANCE_INFO" | awk '/MAIN IP/ {for(i=1;i<=NF;i++) if ($i=="IP") print $(i+1)}')
        break # 跳出循环当状态包含 active
    else
        echo "Instance is not active yet. Waiting for 30 seconds... (Elapsed time: $((ELAPSED_TIME/60)) minutes)" | tee -a "$OUTPUT_FILE"
        sleep 30 # 等待30秒再次检查状态
    fi
done

echo "Instance is active with MAIN IP: $MAIN_IP" | tee -a "$OUTPUT_FILE"

echo "Waiting for 2 minute before logging in..."
sleep 120

# SSH 登陆到主机并禁用UFW防火墙 (确保你有权限无密码登陆)
echo "Disabling UFW firewall on the server..."
timeout 30 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP << EOF
ufw disable
EOF

if [[ $? -eq 0 ]]; then
    echo "UFW firewall has been disabled successfully." | tee -a "$OUTPUT_FILE"
else
    echo "Failed to disable UFW firewall." | tee -a "$OUTPUT_FILE"
fi

# 安装并配置XRay
echo "Installing and configuring XRay..." | tee -a "$OUTPUT_FILE"

# 新安装的VPS上安装XRay
echo "Installing XRay script from GitHub..." | tee -a "$OUTPUT_FILE"
INSTALL_OUTPUT=$(timeout 300 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'bash <(wget -qO- -o- https://github.com/233boy/Xray/raw/main/install.sh)')
INSTALL_STATUS=$?

if [[ $INSTALL_STATUS -eq 124 ]]; then
    echo "XRay installation timed out after 5 minutes." | tee -a "$OUTPUT_FILE"
    exit 1
elif [[ $INSTALL_STATUS -ne 0 ]]; then
    echo "XRay installation failed with error code $INSTALL_STATUS." | tee -a "$OUTPUT_FILE"
    exit 1
fi

echo "$INSTALL_OUTPUT" | tee -a "$OUTPUT_FILE"

# 等待XRay安装完成
sleep 10

# 确认安装完成并创建配置
XRAY_CHECK=$(timeout 30 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'command -v xray')
if [[ -n "$XRAY_CHECK" ]]; then
    echo "XRay installed successfully, creating configuration with schema: $xrayschema" | tee -a "$OUTPUT_FILE"
    # 直接添加配置而不先删除
    CONFIG_OUTPUT=$(timeout 60 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP "xray add $xrayschema")
    CONFIG_STATUS=$?
    
    if [[ $CONFIG_STATUS -eq 124 ]]; then
        echo "XRay configuration creation timed out after 60 seconds." | tee -a "$OUTPUT_FILE"
        exit 1
    elif [[ $CONFIG_STATUS -ne 0 ]]; then
        echo "XRay configuration creation failed with error code $CONFIG_STATUS." | tee -a "$OUTPUT_FILE"
        exit 1
    fi
    
    echo "$CONFIG_OUTPUT" | tee -a "$OUTPUT_FILE"
    
    # 检查XRay服务是否正在运行
    echo "Checking if XRay service is running..." | tee -a "$OUTPUT_FILE"
    SERVICE_STATUS=$(timeout 30 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'systemctl is-active xray || echo "inactive"')
    
    if [[ "$SERVICE_STATUS" == "active" ]]; then
        echo "XRay service is running successfully." | tee -a "$OUTPUT_FILE"
    else
        echo "XRay service is not running. Attempting to start..." | tee -a "$OUTPUT_FILE"
        START_OUTPUT=$(timeout 30 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'systemctl start xray')
        START_STATUS=$?
        
        if [[ $START_STATUS -ne 0 ]]; then
            echo "Failed to start XRay service." | tee -a "$OUTPUT_FILE"
        else
            echo "XRay service started successfully." | tee -a "$OUTPUT_FILE"
        fi
    fi
else
    echo "XRay installation failed or not found." | tee -a "$OUTPUT_FILE"
fi

# 脚本退出时trap会自动发送通知