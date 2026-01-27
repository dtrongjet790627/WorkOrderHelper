# -*- coding: utf-8 -*-
"""SSH执行命令辅助函数"""

import paramiko
from config.database import EAI_SERVER


def ssh_execute_command(command, timeout=30):
    """使用paramiko执行SSH命令

    Args:
        command: 要执行的命令
        timeout: 超时时间（秒）

    Returns:
        tuple: (success, output, error_msg)
    """
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=EAI_SERVER['host'],
            port=EAI_SERVER['port'],
            username=EAI_SERVER['user'],
            password=EAI_SERVER['password'],
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False
        )

        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        output = stdout.read().decode('utf-8', errors='replace')
        error = stderr.read().decode('utf-8', errors='replace')

        return True, output, error
    except paramiko.AuthenticationException:
        return False, '', 'SSH认证失败：用户名或密码错误'
    except paramiko.SSHException as e:
        return False, '', f'SSH连接错误: {str(e)}'
    except Exception as e:
        return False, '', f'连接失败: {str(e)}'
    finally:
        if ssh:
            ssh.close()
