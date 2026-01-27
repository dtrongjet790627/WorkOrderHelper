# -*- coding: utf-8 -*-
"""
Oracle日志表建表脚本执行器
执行create_log_tables.sql中的建表语句
"""
import cx_Oracle

# 连接信息
dsn = cx_Oracle.makedsn('172.17.10.165', 1521, service_name='orcl.ecdag.com')
conn = cx_Oracle.connect(user='iplant_web', password='iplant', dsn=dsn)
cursor = conn.cursor()

print('数据库连接成功!')
print('Oracle版本:', conn.version)

# 定义要执行的SQL语句
sql_statements = [
    # 1. 工单操作日志表
    "CREATE SEQUENCE WOA_WORKORDER_OP_SEQ START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE",

    """CREATE TABLE WOA_WORKORDER_OP (
        ID NUMBER PRIMARY KEY,
        UNITSN NVARCHAR2(100),
        LINENAME NVARCHAR2(20),
        WONO NVARCHAR2(50),
        PARTNO NVARCHAR2(50),
        PRODUCT_STATUS NUMBER,
        OP_TIME DATE DEFAULT SYSDATE,
        OPERATOR NVARCHAR2(50),
        RESULT NVARCHAR2(10),
        REMARK NVARCHAR2(200)
    )""",

    """CREATE OR REPLACE TRIGGER WOA_WORKORDER_OP_TRG
        BEFORE INSERT ON WOA_WORKORDER_OP
        FOR EACH ROW
    BEGIN
        IF :NEW.ID IS NULL THEN
            SELECT WOA_WORKORDER_OP_SEQ.NEXTVAL INTO :NEW.ID FROM DUAL;
        END IF;
    END;""",

    "CREATE INDEX IDX_WOA_WORKORDER_OP_WONO ON WOA_WORKORDER_OP(WONO)",
    "CREATE INDEX IDX_WOA_WORKORDER_OP_UNITSN ON WOA_WORKORDER_OP(UNITSN)",
    "CREATE INDEX IDX_WOA_WORKORDER_OP_TIME ON WOA_WORKORDER_OP(OP_TIME)",

    "COMMENT ON TABLE WOA_WORKORDER_OP IS '工单操作日志表'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.ID IS '主键ID'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.UNITSN IS '产品主码'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.LINENAME IS '产线名称'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.WONO IS '工单号'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.PARTNO IS '产品型号'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.PRODUCT_STATUS IS '产品状态(1=未完成,2=完成)'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.OP_TIME IS '操作时间'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.OPERATOR IS '操作人'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.RESULT IS '操作结果(SUCCESS/FAIL)'",
    "COMMENT ON COLUMN WOA_WORKORDER_OP.REMARK IS '备注信息'",

    # 2. 打包操作日志表
    "CREATE SEQUENCE WOA_PACKING_OP_SEQ START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE",

    """CREATE TABLE WOA_PACKING_OP (
        ID NUMBER PRIMARY KEY,
        UNITSN NVARCHAR2(100),
        LINENAME NVARCHAR2(20),
        WONO NVARCHAR2(50),
        PARTNO NVARCHAR2(50),
        PACKID NVARCHAR2(50),
        PACK_STATUS NUMBER,
        AFFECTED_COUNT NUMBER,
        OP_TYPE NVARCHAR2(20),
        OP_TIME DATE DEFAULT SYSDATE,
        OPERATOR NVARCHAR2(50),
        RESULT NVARCHAR2(10),
        REMARK NVARCHAR2(200)
    )""",

    """CREATE OR REPLACE TRIGGER WOA_PACKING_OP_TRG
        BEFORE INSERT ON WOA_PACKING_OP
        FOR EACH ROW
    BEGIN
        IF :NEW.ID IS NULL THEN
            SELECT WOA_PACKING_OP_SEQ.NEXTVAL INTO :NEW.ID FROM DUAL;
        END IF;
    END;""",

    "CREATE INDEX IDX_WOA_PACKING_OP_WONO ON WOA_PACKING_OP(WONO)",
    "CREATE INDEX IDX_WOA_PACKING_OP_PACKID ON WOA_PACKING_OP(PACKID)",
    "CREATE INDEX IDX_WOA_PACKING_OP_TIME ON WOA_PACKING_OP(OP_TIME)",
    "CREATE INDEX IDX_WOA_PACKING_OP_TYPE ON WOA_PACKING_OP(OP_TYPE)",

    "COMMENT ON TABLE WOA_PACKING_OP IS '打包操作日志表'",
    "COMMENT ON COLUMN WOA_PACKING_OP.ID IS '主键ID'",
    "COMMENT ON COLUMN WOA_PACKING_OP.UNITSN IS '产品主码(批量操作时可为空)'",
    "COMMENT ON COLUMN WOA_PACKING_OP.LINENAME IS '产线名称'",
    "COMMENT ON COLUMN WOA_PACKING_OP.WONO IS '工单号'",
    "COMMENT ON COLUMN WOA_PACKING_OP.PARTNO IS '产品型号'",
    "COMMENT ON COLUMN WOA_PACKING_OP.PACKID IS '批次号'",
    "COMMENT ON COLUMN WOA_PACKING_OP.PACK_STATUS IS '包装状态'",
    "COMMENT ON COLUMN WOA_PACKING_OP.AFFECTED_COUNT IS '影响数量'",
    "COMMENT ON COLUMN WOA_PACKING_OP.OP_TYPE IS '操作类型(EXECUTE_PACKING/GENERATE_PACKID/ADD_MISSING)'",
    "COMMENT ON COLUMN WOA_PACKING_OP.OP_TIME IS '操作时间'",
    "COMMENT ON COLUMN WOA_PACKING_OP.OPERATOR IS '操作人'",
    "COMMENT ON COLUMN WOA_PACKING_OP.RESULT IS '操作结果(SUCCESS/FAIL)'",
    "COMMENT ON COLUMN WOA_PACKING_OP.REMARK IS '备注信息'",

    # 3. HULU同步日志表
    "CREATE SEQUENCE WOA_HULU_SYNC_SEQ START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE",

    """CREATE TABLE WOA_HULU_SYNC (
        ID NUMBER PRIMARY KEY,
        UNITSN NVARCHAR2(100),
        LINENAME NVARCHAR2(20),
        WONO NVARCHAR2(50),
        PARTNO NVARCHAR2(50),
        SYNC_TYPE NVARCHAR2(20),
        ACC_COUNT NUMBER,
        HULU_COUNT NUMBER,
        OP_TIME DATE DEFAULT SYSDATE,
        OPERATOR NVARCHAR2(50),
        RESULT NVARCHAR2(10),
        REMARK NVARCHAR2(200)
    )""",

    """CREATE OR REPLACE TRIGGER WOA_HULU_SYNC_TRG
        BEFORE INSERT ON WOA_HULU_SYNC
        FOR EACH ROW
    BEGIN
        IF :NEW.ID IS NULL THEN
            SELECT WOA_HULU_SYNC_SEQ.NEXTVAL INTO :NEW.ID FROM DUAL;
        END IF;
    END;""",

    "CREATE INDEX IDX_WOA_HULU_SYNC_WONO ON WOA_HULU_SYNC(WONO)",
    "CREATE INDEX IDX_WOA_HULU_SYNC_UNITSN ON WOA_HULU_SYNC(UNITSN)",
    "CREATE INDEX IDX_WOA_HULU_SYNC_TIME ON WOA_HULU_SYNC(OP_TIME)",
    "CREATE INDEX IDX_WOA_HULU_SYNC_TYPE ON WOA_HULU_SYNC(SYNC_TYPE)",

    "COMMENT ON TABLE WOA_HULU_SYNC IS 'HULU同步日志表'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.ID IS '主键ID'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.UNITSN IS '产品主码'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.LINENAME IS '产线名称'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.WONO IS '工单号'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.PARTNO IS '产品型号'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.SYNC_TYPE IS '同步类型(UPDATE/INSERT)'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.ACC_COUNT IS 'ACC数量'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.HULU_COUNT IS 'HULU数量'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.OP_TIME IS '操作时间'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.OPERATOR IS '操作人'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.RESULT IS '操作结果(SUCCESS/FAIL)'",
    "COMMENT ON COLUMN WOA_HULU_SYNC.REMARK IS '备注信息'",
]

# 执行每条SQL语句
success_count = 0
fail_count = 0

for i, sql in enumerate(sql_statements, 1):
    try:
        cursor.execute(sql)
        conn.commit()
        print(f'[{i}/{len(sql_statements)}] 执行成功')
        success_count += 1
    except cx_Oracle.DatabaseError as e:
        error, = e.args
        if error.code == 955:  # ORA-00955: 名称已由现有对象使用
            print(f'[{i}/{len(sql_statements)}] 对象已存在,跳过')
            success_count += 1
        elif error.code == 1430:  # ORA-01430: 列已存在
            print(f'[{i}/{len(sql_statements)}] 已存在,跳过')
            success_count += 1
        elif error.code == 4081:  # 触发器已存在
            print(f'[{i}/{len(sql_statements)}] 触发器已存在,已替换')
            success_count += 1
        else:
            print(f'[{i}/{len(sql_statements)}] 执行失败: {error.message}')
            fail_count += 1

print(f'\n执行完成: 成功 {success_count}, 失败 {fail_count}')

# 验证表创建结果
print('\n=== 验证表创建结果 ===')
cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'WOA_%' ORDER BY table_name")
tables = cursor.fetchall()
print('创建的表:')
for table in tables:
    print(f'  - {table[0]}')

# 验证序列创建结果
print('\n创建的序列:')
cursor.execute("SELECT sequence_name FROM user_sequences WHERE sequence_name LIKE 'WOA_%' ORDER BY sequence_name")
sequences = cursor.fetchall()
for seq in sequences:
    print(f'  - {seq[0]}')

# 验证触发器创建结果
print('\n创建的触发器:')
cursor.execute("SELECT trigger_name FROM user_triggers WHERE trigger_name LIKE 'WOA_%' ORDER BY trigger_name")
triggers = cursor.fetchall()
for trg in triggers:
    print(f'  - {trg[0]}')

# 验证索引创建结果
print('\n创建的索引:')
cursor.execute("SELECT index_name FROM user_indexes WHERE index_name LIKE 'IDX_WOA_%' ORDER BY index_name")
indexes = cursor.fetchall()
for idx in indexes:
    print(f'  - {idx[0]}')

cursor.close()
conn.close()
print('\n数据库连接已关闭')
