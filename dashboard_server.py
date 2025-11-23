from flask import Flask, jsonify, request, session
import subprocess
import threading
import time
import logging
import os
import re
from functools import wraps

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 用于session加密
process_lock = False

# 从conf.env读取密码
def load_password_from_conf():
    """从conf.env文件读取DASHBOARD_PASSWORD"""
    conf_path = './conf.env'
    try:
        if os.path.exists(conf_path):
            with open(conf_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 匹配 DASHBOARD_PASSWORD="xxx" 或 DASHBOARD_PASSWORD='xxx'
                match = re.search(r'DASHBOARD_PASSWORD=["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
        logger.warning("conf.env文件不存在或未找到DASHBOARD_PASSWORD，使用默认密码")
        return "112233@leven"  # 默认密码
    except Exception as e:
        logger.error(f"读取conf.env失败: {str(e)}，使用默认密码")
        return "112233@leven"

SECRET_PASSWORD = load_password_from_conf()

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized access'}), 401
        return f(*args, **kwargs)
    return decorated_function

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

@app.route('/api/login', methods=['POST'])
def login():
    """登录接口"""
    data = request.json
    password = data.get('password', '') if data else ''
    
    if password == SECRET_PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True, 'message': '登录成功'})
    else:
        return jsonify({'success': False, 'error': '密码错误'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """登出接口"""
    session.pop('logged_in', None)
    return jsonify({'success': True, 'message': '已登出'})

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """检查登录状态"""
    return jsonify({'logged_in': session.get('logged_in', False)})

@app.route('/vps/create', methods=['POST'])
@login_required
def create():
    global process_lock

    if process_lock:
        return jsonify({'error': '创建中,请稍后'}), 429

    data = request.json
    region = data.get('region') if data else None
    script_args = []
    if region:
        script_args.extend(['--region', region])

    script_output = run_shell_script('./create-vultr-instance.sh', script_args)
    return jsonify(script_output)

@app.route('/vps/create-and-install', methods=['POST'])
@login_required
def create_and_install():
    global process_lock

    if process_lock:
        return jsonify({'error': '创建中,请稍后'}), 429

    data = request.json or {}
    region = data.get('region', 'nrt')
    xrayschema = data.get('xrayschema', 'reality')
    duration = data.get('duration', '55')  # 添加duration参数，但暂时未使用

    def background_task():
        global process_lock
        process_lock = True

        try:
            # 第一步：创建VPS
            logger.info("开始创建VPS...")
            create_result = run_shell_script('./create-vultr-instance.sh', ['--region', region, '--xrayschema', xrayschema])

            if create_result['exit_code'] != 0:
                logger.error(f"创建VPS失败: {create_result['stderr']}")
                return

            logger.info("VPS创建成功，等待60秒让实例完全启动...")
            time.sleep(60)  # 增加等待时间，确保实例完全就绪

            # 第二步：安装Xray（重装）
            logger.info("开始安装Xray...")
            install_result = run_shell_script('./install-vps.sh', ['--xrayschema', xrayschema])

            if install_result['exit_code'] != 0:
                logger.error(f"安装Xray失败: {install_result['stderr']}")
                return

            logger.info("一键创建和安装完成！")

        except Exception as e:
            logger.error(f"一键创建过程中发生错误: {str(e)}")
        finally:
            process_lock = False

    # 启动后台线程执行完整流程
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()

    return jsonify({'message': '一键创建任务已启动，将在后台完成创建和安装流程'})

@app.route('/vps/remove', methods=['POST'])
@login_required
def remove():
    script_output = run_shell_script('./remove-vultr-instance.sh')
    return jsonify(script_output)

@app.route('/vps/xray', methods=['POST'])
@login_required
def xray():
    data = request.json or {}
    xrayschema = data.get('xrayschema')
    script_args = []
    if xrayschema:
        script_args.extend(['--xrayschema', xrayschema])

    script_output = run_shell_script('./install-vps.sh', script_args)
    return jsonify(script_output)

@app.route('/vps/status', methods=['GET'])
@login_required
def status():
    return jsonify({'in_progress': process_lock})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
