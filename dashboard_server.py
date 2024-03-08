from flask import Flask, jsonify, request
import subprocess

app = Flask(__name__)
SECRET_PASSWORD = "112233@leven"

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

@app.route('/vps/create', methods=['POST'])
def create():
    data = request.json
    if not data or data.get('password') != SECRET_PASSWORD:
        return jsonify({'error': 'Unauthorized access'}), 401
    
    region = data.get('region')
    script_args = []
    if region:
        script_args.extend(['--region', region])

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