from flask import Flask, jsonify, request
import subprocess
import threading
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
SECRET_PASSWORD = "112233@leven"
inporcess_lock=False

def run_shell_script(script_path, args=None):
    if args is None:
        args = []
    
    command = [script_path] + args
    try:
        result = subprocess.run(command, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {
            'stdout': result.stdout.decode('utf-8'),
            'stderr': result.stderr.decode('utf-8'),
            'exit_code': result.returncode
        }
    except subprocess.CalledProcessError as e:
        return {
            'stdout': e.stdout.decode('utf-8'),
            'stderr': e.stderr.decode('utf-8'),
            'exit_code': e.returncode
        }
    
def scheduled_instance_removal(duration):
    # 等待指定的时间
    time.sleep(duration*60)
    inporcess_lock=False
    # 调用销毁脚本
    logger.info(f"Remove VPS instance with region because duration: {duration} min finished")
    run_shell_script('./remove-vultr-instance.sh')

@app.route('/vps/create', methods=['POST'])
def create():
    if inporcess_lock:
        return "创建中,请稍后"
    
    inporcess_lock=True
    data = request.json
    if not data or data.get('password') != SECRET_PASSWORD:
        return jsonify({'error': 'Unauthorized access'}), 401
    
    region = data.get('region')
    script_args = []
    if region:
        script_args.extend(['--region', region])

    duration = int(data.get('duration'))
    if duration < 4:
        duration=55
    
    if duration > 0:
        removal_thread = threading.Thread(target=scheduled_instance_removal, args=(duration,))
        removal_thread.start()

    logger.info(f"Creating VPS instance with region: {region} and duration: {duration} min")
    script_output = run_shell_script('./create-vultr-instance.sh',script_args)
    return jsonify(script_output)

@app.route('/vps/remove', methods=['POST'])
def remove():
    data = request.json
    if not data or data.get('password') != SECRET_PASSWORD:
        return jsonify({'error': 'Unauthorized access'}), 401

    script_output = run_shell_script('./remove-vultr-instance.sh')
    return jsonify(script_output)


@app.route('/vps/xray', methods=['POST'])
def xray():
    data = request.json
    if not data or data.get('password') != SECRET_PASSWORD:
        return jsonify({'error': 'Unauthorized access'}), 401

    xrayschema = data.get('xrayschema')
    script_args = []
    if xrayschema:
        script_args.extend(['--xrayschema', xrayschema])

    script_output = run_shell_script('./install-vps.sh',script_args)
    return jsonify(script_output)

if __name__ == '__main__':
    app.run(debug=True)