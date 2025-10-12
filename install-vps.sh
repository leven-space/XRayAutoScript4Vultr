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

install_and_configure_xray() {
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

  # 检查 XRay 是否已安装
  echo "Checking if XRay is already installed on $MAIN_IP..." | tee -a "$OUTPUT_FILE"
  XRAY_CHECK=$(timeout 30 ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" 'command -v xray || echo "not_installed"')
  
  if [[ "$XRAY_CHECK" == "not_installed" ]]; then
    # 运行 GitHub 上的 xray 安装脚本
    echo "XRay not installed. Running install script from GitHub on $MAIN_IP..." | tee -a "$OUTPUT_FILE"
    INSTALL_OUTPUT=$(timeout 300 ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" 'bash <(wget -qO- https://github.com/233boy/Xray/raw/main/install.sh)')
    INSTALL_STATUS=$?
    if [[ $INSTALL_STATUS -eq 124 ]]; then
      echo "XRay installation timed out after 5 minutes on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "XRay installation timed out on $MAIN_IP. Please check the server manually."
      return 1
    elif [[ $INSTALL_STATUS -ne 0 ]]; then
      echo "XRay installation failed with error code $INSTALL_STATUS on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "XRay installation failed on $MAIN_IP. Please check the server manually."
      return 1
    fi
    echo "$INSTALL_OUTPUT" | tee -a "$OUTPUT_FILE"
  else
    echo "XRay is already installed on $MAIN_IP." | tee -a "$OUTPUT_FILE"
  fi

  # 检查配置文件是否存在
  CONFIG_CHECK=$(timeout 30 ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" 'ls -1 /etc/xray/ | grep -c json || echo "0"')
  
  echo "Creating new XRay configuration with schema: $xrayschema" | tee -a "$OUTPUT_FILE"
  if [[ "$CONFIG_CHECK" != "0" ]]; then
    # 存在配置文件，保留现有配置并添加新配置
    echo "Existing configuration found. Adding new configuration..." | tee -a "$OUTPUT_FILE"
    CONFIG_OUTPUT=$(timeout 60 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP "xray add $xrayschema")
    CONFIG_STATUS=$?
    if [[ $CONFIG_STATUS -eq 124 ]]; then
      echo "XRay configuration creation timed out after 60 seconds on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "XRay configuration creation timed out on $MAIN_IP. Please check the server manually."
      return 1
    elif [[ $CONFIG_STATUS -ne 0 ]]; then
      echo "XRay configuration creation failed with error code $CONFIG_STATUS on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "XRay configuration creation failed on $MAIN_IP. Please check the server manually."
      return 1
    fi
    echo "$CONFIG_OUTPUT" | tee -a "$OUTPUT_FILE"
  else
    # 不存在配置文件，直接添加新配置
    echo "No existing configuration found. Creating new configuration..." | tee -a "$OUTPUT_FILE"
    CONFIG_OUTPUT=$(timeout 60 ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH root@$MAIN_IP "xray add $xrayschema")
    CONFIG_STATUS=$?
    if [[ $CONFIG_STATUS -eq 124 ]]; then
      echo "XRay configuration creation timed out after 60 seconds on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "XRay configuration creation timed out on $MAIN_IP. Please check the server manually."
      return 1
    elif [[ $CONFIG_STATUS -ne 0 ]]; then
      echo "XRay configuration creation failed with error code $CONFIG_STATUS on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "XRay configuration creation failed on $MAIN_IP. Please check the server manually."
      return 1
    fi
    echo "$CONFIG_OUTPUT" | tee -a "$OUTPUT_FILE"
  fi
  
  # 检查XRay是否正在运行
  echo "Checking if XRay service is running on $MAIN_IP..." | tee -a "$OUTPUT_FILE"
  SERVICE_STATUS=$(timeout 30 ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" 'systemctl is-active xray || echo "inactive"')
  if [[ "$SERVICE_STATUS" == "active" ]]; then
    echo "XRay service is running on $MAIN_IP." | tee -a "$OUTPUT_FILE"
  else
    echo "XRay service is not running on $MAIN_IP. Attempting to start..." | tee -a "$OUTPUT_FILE"
    START_OUTPUT=$(timeout 30 ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" root@"$MAIN_IP" 'systemctl start xray')
    START_STATUS=$?
    if [[ $START_STATUS -ne 0 ]]; then
      echo "Failed to start XRay service on $MAIN_IP." | tee -a "$OUTPUT_FILE"
      send_dingtalk_message "Failed to start XRay service on $MAIN_IP. Please check the server manually."
      return 1
    fi
    echo "XRay service started on $MAIN_IP." | tee -a "$OUTPUT_FILE"
  fi
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
          
          # 确保即使安装失败也会继续处理其他实例
          if ! install_and_configure_xray $MAIN_IP; then
            echo "Failed to complete installation on $MAIN_IP. Continuing with other instances..." | tee -a "$OUTPUT_FILE"
          fi
        fi
        # 等待一段时间，以防API限制速率（可选）
        sleep 5
    done
fi



# 优化推送内容：优先推送VLESS链接
MESSAGE_CONTENT=$(<"$OUTPUT_FILE")
VLESS_LINK=$(echo "$MESSAGE_CONTENT" | grep -oE 'vless://[^\s\\"]+')
if [[ -n "$VLESS_LINK" ]]; then
  send_dingtalk_message "VLESS链接: $VLESS_LINK"
else
  send_dingtalk_message "$MESSAGE_CONTENT"
fi

# 清理：删除临时文件
rm "$OUTPUT_FILE"

exit 0 # 脚本执行成功结束退出码为0.