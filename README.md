# ACC工单管理系统 - ERP收货处理

## 功能说明

1. **工单查询** - 输入工单号，查看工单完成情况
   - 显示总数量、已完工、未完工、完成率
   - 自动识别产线并连接对应数据库

2. **打包信息展示** - 显示工单的打包情况
   - 批次号、实际数量、包装规格
   - 封包状态、最后更新时间

3. **ERP收货对比** - 上传ERP导出的Excel文件
   - 自动解析并与数据库对比
   - 显示各批次差异

4. **数据同步** - 根据ERP数据调整数据库
   - 删除多余记录
   - 补充缺失记录

## 部署步骤

### 1. 安装Python环境
```bash
# CentOS/RHEL
yum install python3 python3-pip

# Ubuntu/Debian
apt install python3 python3-pip
```

### 2. 安装Oracle Instant Client
```bash
# 下载并安装Oracle Instant Client
# https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html

# 设置环境变量
export LD_LIBRARY_PATH=/opt/oracle/instantclient_21_1:$LD_LIBRARY_PATH
```

### 3. 安装依赖
```bash
cd /path/to/web_app
pip3 install -r requirements.txt
```

### 4. 启动应用
```bash
# 开发模式
python3 app.py

# 生产模式（使用gunicorn）
pip3 install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 5. 访问应用
浏览器打开: http://服务器IP:5000

## 配置说明

### 数据库配置 (app.py)
```python
DB_CONFIG = {
    'host': '172.17.10.165',
    'port': 1521,
    'service_name': 'orcl.ecdag.com'
}
```

### 产线用户配置
| 产线 | 用户名 | 工单前缀 |
|------|--------|----------|
| 电控一线 | iplant_dpepp1 | SMT/MID/EPP |
| 电控二线 | iplant_smt2 | SMT-2/MID-2 |
| 总成DP产线 | iplant_dpeps1 | EPS/IPA |
| 总成C产线 | iplant_ceps1 | C |

## 使用说明

### 1. 查询工单
- 输入工单号（如: SMT25121001）
- 点击"查询"按钮
- 查看工单完成情况和打包信息

### 2. 对比ERP数据
- 从ERP导出生产汇报单Excel
- 点击"选择文件"上传
- 点击"解析文件"查看对比结果

### 3. 执行同步
- 查看对比结果中的差异
- 点击"执行同步"删除多余记录
- 点击"补充缺失记录"添加缺失数据

## 注意事项

1. Excel文件使用"完成数量"字段（第14列），而非"合格品入库数量"
2. 同步操作会直接修改数据库，请谨慎操作
3. 操作日志会记录所有执行的操作

## 文件结构
```
web_app/
├── app.py              # Flask应用主程序
├── requirements.txt    # Python依赖
├── README.md           # 部署说明
└── templates/
    └── index.html      # 前端页面
```

## 系统服务配置（可选）

### systemd服务
创建文件 `/etc/systemd/system/acc-workorder.service`:
```ini
[Unit]
Description=ACC Workorder Management System
After=network.target

[Service]
User=root
WorkingDirectory=/path/to/web_app
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启用服务:
```bash
systemctl daemon-reload
systemctl enable acc-workorder
systemctl start acc-workorder
```
