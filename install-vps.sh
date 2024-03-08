#!/bin/bash

# 导入配置文件
source ./conf.env

# 创建临时文件用于存储输出信息
OUTPUT_FILE=$(mktemp)

# 默认值
xrayschema=reality

# 解析命令行选项和参数
while [[ "$#" -gt 0 ]]; do
    case $1 in
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

disable_ufw_and_install_xray() {
  local MAIN_IP="$1"

  # 禁用 UFW 防火墙
  echo "Disabling UFW firewall on the server $MAIN_IP..."
  ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" << EOF
ufw disable
EOF

  if [[ $? -eq 0 ]]; then
      echo "UFW firewall has been disabled successfully on $MAIN_IP." | tee -a "$OUTPUT_FILE"
  else
      echo "Failed to disable UFW firewall on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      return 1 # 返回错误状态码，终止函数执行
  fi

  # 运行 GitHub 上的 xray 安装脚本
  echo "Running install xray script from GitHub on $MAIN_IP..." | tee -a "$OUTPUT_FILE"
  INSTALL_OUTPUT=$(ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" 'bash <(wget -qO- https://github.com/233boy/Xray/raw/main/install.sh)')
  echo "Running xray to create tcp" | tee -a "$OUTPUT_FILE"
  ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'xray del' | tee -a "$OUTPUT_FILE"
  ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP 'xray add ' $xrayschema | tee -a "$OUTPUT_FILE"
  echo "$INSTALL_OUTPUT" | tee -a "$OUTPUT_FILE"
}


# 获取所有实例列表
echo "Retrieving all instances..." | tee -a "$OUTPUT_FILE"
INSTANCE_IDS=$($VULTR_CLI instance list | awk '/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/ {print $1}')

# 检查是否获取到任何实例ID
if [ -z "$INSTANCE_IDS" ]; then
    echo "install vps,but No instances found." | tee -a "$OUTPUT_FILE"
else
    # 遍历所有实例,并安装vps
    for INSTANCE_ID in $INSTANCE_IDS; do
        echo "install vps for  instance ID: $INSTANCE_ID..." | tee -a "$OUTPUT_FILE"
        INSTANCE_INFO=$($VULTR_CLI instance get $INSTANCE_ID)
        STATUS=$(echo "$INSTANCE_INFO" | grep -io 'STATUS\s\+active') # 使用正则表达式匹配 STATUS 和 active

        if [[ $STATUS ]]; then # 检查是否有匹配
          # 使用 awk 正则表达式来匹配 MAIN IP 后跟随的IP地址
          MAIN_IP=$(echo "$INSTANCE_INFO" | awk '/MAIN IP/ {for(i=1;i<=NF;i++) if ($i=="IP") print $(i+1)}')
          echo "Instance is active with MAIN IP: $MAIN_IP" | tee -a "$OUTPUT_FILE"
	      disable_ufw_and_install_xray $MAIN_IP
        fi
        # 等待一段时间，以防API限制速率（可选）
        sleep 5
    done
fi


# 将临时文件内容读取到变量中，并发送通知消息至钉钉群组机器人
MESSAGE_CONTENT=$(<"$OUTPUT_FILE")
send_dingtalk_message "$MESSAGE_CONTENT"

# 清理：删除临时文件
rm "$OUTPUT_FILE"

exit 0 # 脚本执行成功结束退出码为0.