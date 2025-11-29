from flask import Flask, jsonify, request, session
import subprocess
import threading
import time
import logging
import os
import re
import json
import hashlib
from functools import wraps
from datetime import datetime, timedelta

# 配置日志 - 同时输出到文件和控制台
LOG_FILE = './dashboard_server.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 创建logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 设置最低日志级别

# 清除已有的处理器（避免重复添加）
logger.handlers.clear()

# 文件处理器 - 记录所有级别的日志，使用追加模式
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 控制台处理器 - 只显示INFO及以上级别
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# 防止日志传播到根logger（避免重复输出）
logger.propagate = False

logger.info(f"日志系统已初始化，日志文件: {os.path.abspath(LOG_FILE)}")

# ============ 常量定义 ============
VPS_STARTUP_WAIT_SECONDS = 60          # VPS启动等待时间（秒）
DEFAULT_VPS_DURATION_MINUTES = 55      # 默认VPS运行时长（分钟）
SCHEDULE_CHECK_INTERVAL_SECONDS = 60   # 定时检查间隔（秒）
MIN_VPS_DURATION_MINUTES = 1           # 最小VPS运行时长（分钟）

app = Flask(__name__)

# 使用固定的 secret_key，基于机器特征生成或从环境变量读取
def get_secret_key():
    """获取或生成固定的 secret_key"""
    env_key = os.environ.get('FLASK_SECRET_KEY')
    if env_key:
        return env_key
    # 基于机器名和固定盐值生成稳定的 key
    machine_id = os.environ.get('COMPUTERNAME', 'default') + '-xray-dashboard'
    return hashlib.sha256(machine_id.encode()).hexdigest()

app.secret_key = get_secret_key()

# 使用 threading.Lock 替代布尔值，确保线程安全
process_lock = threading.Lock()
# 存储当前任务状态信息
current_task_info = {
    'in_progress': False,
    'start_time': None,
    'stage': None,  # 'creating', 'waiting', 'installing', None
    'region': None,
    'xrayschema': None
}
task_info_lock = threading.Lock()

# 存储VPS创建时间和到期时间的字典
# 格式: {instance_id: {'create_time': datetime_str, 'duration_minutes': int}}
vps_schedule = {}
vps_schedule_lock = threading.Lock()
SCHEDULE_FILE = './vps_schedule.json'

def save_schedule():
    """保存调度信息到文件"""
    try:
        with vps_schedule_lock:
            # 转换datetime为字符串以便JSON序列化
            schedule_data = {}
            for k, v in vps_schedule.items():
                schedule_data[k] = {
                    'create_time': v['create_time'].isoformat(),
                    'duration_minutes': v['duration_minutes']
                }
            with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                json.dump(schedule_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存调度信息失败: {str(e)}")

def load_schedule():
    """从文件加载调度信息"""
    global vps_schedule
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                schedule_data = json.load(f)
            with vps_schedule_lock:
                for k, v in schedule_data.items():
                    vps_schedule[k] = {
                        'create_time': datetime.fromisoformat(v['create_time']),
                        'duration_minutes': v['duration_minutes']
                    }
            logger.info(f"已加载 {len(vps_schedule)} 个调度任务")
    except Exception as e:
        logger.error(f"加载调度信息失败: {str(e)}")

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
    """执行shell脚本，返回执行结果"""
    if args is None:
        args = []
    
    # 确保脚本路径是绝对路径，或者相对于当前工作目录
    if not os.path.isabs(script_path):
        # 如果是相对路径，确保相对于脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, script_path.lstrip('./'))
    
    # 检查脚本文件是否存在
    if not os.path.exists(script_path):
        logger.error(f"脚本文件不存在: {script_path}")
        return {
            'stdout': '',
            'stderr': f'脚本文件不存在: {script_path}',
            'exit_code': -1
        }
    
    # 在Linux环境下，使用bash执行脚本
    # 确保脚本有执行权限（如果是在Linux上运行）
    command = ['bash', script_path] + args
    
    try:
        logger.debug(f"执行脚本: {' '.join(command)}")
        result = subprocess.run(command, check=False,  # 不抛出异常，手动检查返回码
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=300)  # 设置5分钟超时，防止脚本卡死
        stdout_str = result.stdout.decode('utf-8', errors='replace')
        stderr_str = result.stderr.decode('utf-8', errors='replace')
        
        return {
            'stdout': stdout_str,
            'stderr': stderr_str,
            'exit_code': result.returncode
        }
    except subprocess.TimeoutExpired:
        logger.error(f"脚本执行超时: {script_path}")
        return {
            'stdout': '',
            'stderr': f'脚本执行超时（超过5分钟）: {script_path}',
            'exit_code': -4
        }
    except FileNotFoundError:
        logger.error(f"bash命令不存在，可能不在Linux环境: {script_path}")
        return {
            'stdout': '',
            'stderr': f'bash命令不存在，可能不在Linux环境: {script_path}',
            'exit_code': -1
        }
    except PermissionError:
        logger.error(f"没有执行权限: {script_path}")
        return {
            'stdout': '',
            'stderr': f'没有执行权限: {script_path}',
            'exit_code': -2
        }
    except Exception as e:
        logger.error(f"执行脚本时发生未知错误: {str(e)}", exc_info=True)
        return {
            'stdout': '',
            'stderr': f'执行脚本时发生错误: {str(e)}',
            'exit_code': -3
        }

def scheduled_instance_removal():
    """后台线程：定期检查并删除到期的VPS实例"""
    logger.info("定时删除线程已启动，开始监控VPS实例...")
    while True:
        try:
            current_time = datetime.now()
            should_remove_all = False
            instances_to_remove = []
            
            # 检查哪些VPS需要删除
            with vps_schedule_lock:
                schedule_count = len(vps_schedule)
                if schedule_count > 0:
                    logger.debug(f"当前有 {schedule_count} 个VPS实例在监控列表中")
                
                for instance_id, schedule_info in list(vps_schedule.items()):
                    create_time = schedule_info['create_time']
                    duration_minutes = schedule_info['duration_minutes']
                    expire_time = create_time + timedelta(minutes=duration_minutes)
                    remaining_seconds = (expire_time - current_time).total_seconds()
                    
                    logger.debug(f"检查实例 {instance_id}: 创建时间={create_time}, 到期时间={expire_time}, 剩余时间={remaining_seconds:.0f}秒")
                    
                    if current_time >= expire_time:
                        if instance_id == '__all_instances__':
                            should_remove_all = True
                            logger.warning(f"定时删除任务已到期，将删除所有VPS实例 (创建时间: {create_time}, 运行时长: {duration_minutes}分钟, 当前时间: {current_time})")
                        else:
                            instances_to_remove.append(instance_id)
                            logger.warning(f"VPS {instance_id} 已到期，将在下次检查时删除 (创建时间: {create_time}, 运行时长: {duration_minutes}分钟, 当前时间: {current_time})")
            
            # 如果有到期的实例，执行删除
            if should_remove_all or instances_to_remove:
                if should_remove_all:
                    logger.warning("开始删除所有VPS实例（定时任务到期）...")
                else:
                    logger.warning(f"开始删除 {len(instances_to_remove)} 个到期的VPS实例: {instances_to_remove}")
                
                remove_result = run_shell_script('./remove-vultr-instance.sh')
                
                logger.info(f"删除脚本执行结果: exit_code={remove_result['exit_code']}, stdout={remove_result['stdout'][:200]}, stderr={remove_result['stderr'][:200]}")
                
                if remove_result['exit_code'] == 0:
                    # 删除成功后，从调度字典中移除
                    with vps_schedule_lock:
                        if should_remove_all:
                            vps_schedule.pop('__all_instances__', None)
                            logger.info("已从调度列表中移除 '__all_instances__' 任务")
                        for instance_id in instances_to_remove:
                            vps_schedule.pop(instance_id, None)
                            logger.info(f"已从调度列表中移除实例 {instance_id}")
                    save_schedule()  # 保存到文件
                    logger.warning(f"成功删除到期的VPS实例，已更新调度列表")
                else:
                    logger.error(f"删除VPS实例失败 (exit_code={remove_result['exit_code']}): stdout={remove_result['stdout']}, stderr={remove_result['stderr']}")
            else:
                # 定期记录监控状态（每10次检查记录一次，避免日志过多）
                if not hasattr(scheduled_instance_removal, '_check_count'):
                    scheduled_instance_removal._check_count = 0
                scheduled_instance_removal._check_count += 1
                if scheduled_instance_removal._check_count % 10 == 0:
                    with vps_schedule_lock:
                        if len(vps_schedule) > 0:
                            logger.info(f"定时删除线程运行正常，当前监控 {len(vps_schedule)} 个VPS实例")
            
            # 定期检查
            time.sleep(SCHEDULE_CHECK_INTERVAL_SECONDS)
            
        except Exception as e:
            logger.error(f"定时删除检查过程中发生错误: {str(e)}", exc_info=True)
            time.sleep(SCHEDULE_CHECK_INTERVAL_SECONDS)

def start_removal_thread():
    """启动定时删除后台线程"""
    try:
        load_schedule()  # 加载之前保存的调度信息
        removal_thread = threading.Thread(target=scheduled_instance_removal, name="VPSRemovalThread")
        removal_thread.daemon = True
        removal_thread.start()
        logger.info(f"定时删除后台线程已启动 (线程ID: {removal_thread.ident}, 监控间隔: {SCHEDULE_CHECK_INTERVAL_SECONDS}秒)")
        
        # 验证线程是否真的在运行
        import time as time_module
        time_module.sleep(0.1)  # 短暂等待
        if removal_thread.is_alive():
            logger.info("定时删除线程已确认运行中")
        else:
            logger.error("警告：定时删除线程启动后立即退出，可能存在问题！")
    except Exception as e:
        logger.error(f"启动定时删除线程失败: {str(e)}", exc_info=True)

@app.route('/vps/api/login', methods=['POST'])
def login():
    """登录接口"""
    data = request.json
    password = data.get('password', '') if data else ''
    
    if password == SECRET_PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True, 'message': '登录成功'})
    else:
        return jsonify({'success': False, 'error': '密码错误'}), 401

@app.route('/vps/api/logout', methods=['POST'])
def logout():
    """登出接口"""
    session.pop('logged_in', None)
    return jsonify({'success': True, 'message': '已登出'})

@app.route('/vps/api/check-auth', methods=['GET'])
def check_auth():
    """检查登录状态"""
    return jsonify({'logged_in': session.get('logged_in', False)})

@app.route('/vps/api/create', methods=['POST'])
@login_required
def create():
    # 尝试获取锁，如果获取失败说明有任务在执行
    if not process_lock.acquire(blocking=False):
        return jsonify({'error': '创建中,请稍后'}), 429

    try:
        data = request.json
        region = data.get('region') if data else None
        script_args = []
        if region:
            script_args.extend(['--region', region])

        script_output = run_shell_script('./create-vultr-instance.sh', script_args)
        return jsonify(script_output)
    finally:
        process_lock.release()

@app.route('/vps/api/create-and-install', methods=['POST'])
@login_required
def create_and_install():
    # 尝试获取锁，如果获取失败说明有任务在执行
    if not process_lock.acquire(blocking=False):
        return jsonify({'error': '创建中,请稍后'}), 429

    data = request.json or {}
    region = data.get('region', 'nrt')
    xrayschema = data.get('xrayschema', 'reality')
    
    # 安全地解析 duration 参数
    try:
        duration = int(data.get('duration', str(DEFAULT_VPS_DURATION_MINUTES)))
        if duration < MIN_VPS_DURATION_MINUTES:
            duration = DEFAULT_VPS_DURATION_MINUTES
    except (ValueError, TypeError):
        duration = DEFAULT_VPS_DURATION_MINUTES

    def update_task_info(in_progress, stage=None):
        """更新任务状态信息"""
        with task_info_lock:
            current_task_info['in_progress'] = in_progress
            current_task_info['stage'] = stage
            if in_progress and stage == 'creating':
                current_task_info['start_time'] = datetime.now().isoformat()
                current_task_info['region'] = region
                current_task_info['xrayschema'] = xrayschema
            elif not in_progress:
                current_task_info['start_time'] = None
                current_task_info['region'] = None
                current_task_info['xrayschema'] = None

    def background_task():
        try:
            update_task_info(True, 'creating')
            
            # 第一步：创建VPS
            logger.info("开始创建VPS...")
            create_result = run_shell_script('./create-vultr-instance.sh', ['--region', region, '--xrayschema', xrayschema])

            if create_result['exit_code'] != 0:
                logger.error(f"创建VPS失败: {create_result['stderr']}")
                return

            # 从创建结果中提取实例ID
            instance_id = None
            stdout_lines = create_result['stdout'].split('\n')
            for line in stdout_lines:
                if 'Instance created with ID:' in line or 'ID:' in line:
                    # 尝试提取UUID格式的实例ID
                    uuid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', line)
                    if uuid_match:
                        instance_id = uuid_match.group(0)
                        break
            
            # 如果无法从输出中提取，尝试从整个输出中搜索UUID
            if not instance_id:
                uuid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', create_result['stdout'])
                if uuid_match:
                    instance_id = uuid_match.group(0)

            # 关键修复：在VPS创建成功后立即记录创建时间，而不是在安装完成后
            # 这样确保用户设置的运行时长是从VPS创建时开始计算的
            create_time = datetime.now()
            
            # 如果成功创建并获取到实例ID，立即记录到定时删除列表
            if instance_id:
                with vps_schedule_lock:
                    vps_schedule[instance_id] = {
                        'create_time': create_time,
                        'duration_minutes': duration
                    }
                save_schedule()  # 保存到文件
                expire_time = create_time + timedelta(minutes=duration)
                logger.info(f"VPS {instance_id} 已添加到定时删除列表，将在 {expire_time} 自动删除 (运行时长: {duration}分钟, 创建时间: {create_time})")
            else:
                # 如果仍然无法获取实例ID，记录创建时间，定时删除时会删除所有实例
                logger.warning("未能从创建结果中提取实例ID，将在到期时删除所有实例")
                with vps_schedule_lock:
                    # 使用特殊键来标记需要删除所有实例
                    vps_schedule['__all_instances__'] = {
                        'create_time': create_time,
                        'duration_minutes': duration
                    }
                save_schedule()  # 保存到文件
                expire_time = create_time + timedelta(minutes=duration)
                logger.info(f"将在 {expire_time} 自动删除所有VPS实例 (运行时长: {duration}分钟, 创建时间: {create_time})")

            update_task_info(True, 'waiting')
            logger.info(f"VPS创建成功，等待{VPS_STARTUP_WAIT_SECONDS}秒让实例完全启动...")
            time.sleep(VPS_STARTUP_WAIT_SECONDS)

            # 第二步：安装Xray（重装）
            update_task_info(True, 'installing')
            logger.info("开始安装Xray...")
            install_result = run_shell_script('./install-vps.sh', ['--xrayschema', xrayschema])

            if install_result['exit_code'] != 0:
                logger.error(f"安装Xray失败: {install_result['stderr']}")
                # 注意：即使安装失败，定时删除任务已经记录，VPS仍会在到期时被删除
                return

            logger.info("一键创建和安装完成！")

        except Exception as e:
            logger.error(f"一键创建过程中发生错误: {str(e)}")
        finally:
            update_task_info(False)
            process_lock.release()

    # 启动后台线程执行完整流程
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()

    return jsonify({'message': '一键创建任务已启动，将在后台完成创建和安装流程'})

@app.route('/vps/api/remove', methods=['POST'])
@login_required
def remove():
    script_output = run_shell_script('./remove-vultr-instance.sh')
    
    # 手动删除后清空调度字典
    if script_output['exit_code'] == 0:
        with vps_schedule_lock:
            vps_schedule.clear()
        save_schedule()
        logger.info("手动删除VPS成功，已清空定时删除调度")
    
    return jsonify(script_output)

@app.route('/vps/api/xray', methods=['POST'])
@login_required
def xray():
    data = request.json or {}
    xrayschema = data.get('xrayschema')
    script_args = []
    if xrayschema:
        script_args.extend(['--xrayschema', xrayschema])

    script_output = run_shell_script('./install-vps.sh', script_args)
    return jsonify(script_output)

@app.route('/vps/api/status', methods=['GET'])
@login_required
def status():
    """获取当前任务状态"""
    with task_info_lock:
        return jsonify({
            'in_progress': current_task_info['in_progress'],
            'start_time': current_task_info['start_time'],
            'stage': current_task_info['stage'],
            'region': current_task_info['region'],
            'xrayschema': current_task_info['xrayschema']
        })

@app.route('/vps/api/schedule', methods=['GET'])
@login_required
def get_schedule():
    """获取定时删除调度信息"""
    with vps_schedule_lock:
        result = []
        current_time = datetime.now()
        for instance_id, info in vps_schedule.items():
            expire_time = info['create_time'] + timedelta(minutes=info['duration_minutes'])
            remaining_seconds = max(0, (expire_time - current_time).total_seconds())
            result.append({
                'instance_id': instance_id,
                'create_time': info['create_time'].isoformat(),
                'expire_time': expire_time.isoformat(),
                'duration_minutes': info['duration_minutes'],
                'remaining_seconds': int(remaining_seconds),
                'is_all_instances': instance_id == '__all_instances__'
            })
    return jsonify(result)

@app.route('/vps/api/schedule/<instance_id>', methods=['DELETE'])
@login_required
def cancel_schedule(instance_id):
    """取消指定实例的定时删除任务"""
    with vps_schedule_lock:
        if instance_id in vps_schedule:
            del vps_schedule[instance_id]
            save_schedule()
            logger.info(f"已取消实例 {instance_id} 的定时删除任务")
            return jsonify({'success': True, 'message': f'已取消实例 {instance_id} 的定时删除任务'})
        else:
            return jsonify({'success': False, 'error': '未找到该实例的定时删除任务'}), 404

# 启动定时删除线程的逻辑
# 避免在Flask debug模式下reloader导致启动两次
def init_removal_thread():
    """初始化定时删除线程（只启动一次）"""
    # 检查是否已经启动过
    if not hasattr(init_removal_thread, '_started'):
        init_removal_thread._started = True
        logger.info("正在初始化定时删除线程...")
        start_removal_thread()
    else:
        logger.debug("定时删除线程已经启动过，跳过重复启动")

# 确保线程总是启动（无论什么模式）
# 在非debug模式或作为WSGI应用时直接启动
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not os.environ.get('FLASK_DEBUG'):
    logger.info("检测到非debug模式或WERKZEUG_RUN_MAIN=true，启动定时删除线程")
    init_removal_thread()
else:
    logger.info("检测到debug模式，将在主进程中启动定时删除线程")

if __name__ == '__main__':
    # 在debug模式下，只在reloader子进程中启动
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        logger.info("在debug模式的主进程中启动定时删除线程")
        init_removal_thread()
    else:
        # 如果不在reloader子进程，也尝试启动（作为备用）
        logger.info("不在reloader子进程，尝试启动定时删除线程（备用）")
        init_removal_thread()
    app.run(debug=True, host='0.0.0.0', port=5000)
