#!/bin/bash


# 导入配置文件
source ./conf.env

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

# 创建临时文件用于存储输出信息
OUTPUT_FILE=$(mktemp)

# 获取所有实例列表
echo "Retrieving all instances..." | tee -a "$OUTPUT_FILE"
INSTANCE_IDS=$($VULTR_CLI instance list | awk '/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/ {print $1}')

echo $INSTANCE_IDS
# 检查是否获取到任何实例ID
if [ -z "$INSTANCE_IDS" ]; then
    echo "No instances found." | tee -a "$OUTPUT_FILE"
else
    # 遍历所有实例ID并尝试删除它们
    for INSTANCE_ID in $INSTANCE_IDS; do
        echo "Deleting instance ID: $INSTANCE_ID..." | tee -a "$OUTPUT_FILE"

        # 执行删除操作（这里假设 vultr-cli 的语法是正确的）
        DELETE_OUTPUT=$($VULTR_CLI instance delete "$INSTANCE_ID")

        if [ $? -eq 0 ]; then
            echo "Instance ID: $INSTANCE_ID deleted successfully." | tee -a "$OUTPUT_FILE"
        else
            echo "Failed to delete instance ID: $INSTANCE_ID. Error: $DELETE_OUTPUT" | tee -a "$OUTPUT_FILE"
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
