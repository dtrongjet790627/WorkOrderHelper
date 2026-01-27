#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署app.py到165服务器并重启服务
韩大师 - ACC运维
"""

import paramiko
import os

# 服务器配置
SERVER = '172.17.10.165'
USERNAME = 'administrator'
PASSWORD = 'zjHangqu321'

# 文件路径
LOCAL_FILE = r'D:\TechTeam\Delivery\ACC运维\2025-12-28_ERP收货不足处理\web_app\app.py'
REMOTE_FILE = r'D:\acc_workorder_system\app.py'

# 服务名称
SERVICE_NAME = 'ACC_ERP_Tool'

def main():
    print(f"[1/4] 连接到服务器 {SERVER}...")

    # 创建SSH客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(SERVER, username=USERNAME, password=PASSWORD, timeout=30)
        print(f"      连接成功!")

        # 创建SFTP客户端
        print(f"[2/4] 上传文件...")
        print(f"      本地: {LOCAL_FILE}")
        print(f"      远程: {REMOTE_FILE}")

        sftp = ssh.open_sftp()
        sftp.put(LOCAL_FILE, REMOTE_FILE)
        sftp.close()
        print(f"      上传成功!")

        # 停止服务
        print(f"[3/4] 停止服务 {SERVICE_NAME}...")
        stdin, stdout, stderr = ssh.exec_command(f'net stop "{SERVICE_NAME}"', timeout=60)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode('gbk', errors='ignore')
        error = stderr.read().decode('gbk', errors='ignore')
        if output:
            print(f"      {output.strip()}")
        if error and '已经启动' not in error and '成功' not in output:
            print(f"      {error.strip()}")

        # 启动服务
        print(f"[4/4] 启动服务 {SERVICE_NAME}...")
        stdin, stdout, stderr = ssh.exec_command(f'net start "{SERVICE_NAME}"', timeout=60)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode('gbk', errors='ignore')
        error = stderr.read().decode('gbk', errors='ignore')
        if output:
            print(f"      {output.strip()}")
        if error:
            print(f"      {error.strip()}")

        # 验证服务状态
        print(f"\n[验证] 检查服务状态...")
        stdin, stdout, stderr = ssh.exec_command(f'sc query "{SERVICE_NAME}"', timeout=30)
        output = stdout.read().decode('gbk', errors='ignore')
        if 'RUNNING' in output:
            print(f"      服务运行正常!")
        else:
            print(f"      服务状态:\n{output}")

        print("\n" + "="*50)
        print("部署完成!")
        print("="*50)
        print("\n修复内容：")
        print("- 修复EAI日志按工单号查询时的渲染错乱问题")
        print("- 按工单号过滤时只展开包含该工单号的trigger记录")
        print("- 避免rowspan计算错误导致表格渲染错乱")

    except Exception as e:
        print(f"错误: {e}")
        raise
    finally:
        ssh.close()

if __name__ == '__main__':
    main()
