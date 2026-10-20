## ADDED Requirements

### Requirement: 主动内容不在应用同源执行
文件预览 SHALL 仅允许已确认的栅格格式和UTF-8纯文本；HTML、SVG及未知格式 MUST 下载，并设置nosniff和sandbox CSP。

#### Scenario: 用户上传HTML并共享
- **WHEN** 另一账号查看其有权限的HTML文件
- **THEN** 返回下载且脚本不在应用同源执行

### Requirement: IMAP账号绑定
服务器IMAP连接 SHALL 显式绑定唯一账号；配置缺失或其他账号 MUST 在网络连接前被拒绝。

#### Scenario: 非绑定账号发起扫描
- **WHEN** 已登录的其他账号调用扫描
- **THEN** 返回拒绝，未连接或导入服务器邮箱

### Requirement: AI使用额度及并发
AI对话、转写及重建索引 SHALL 执行账号级原子配额，0与负数 MUST 被配置校验拒绝。queued/running任务数 SHALL 在账号行锁内判断；查询和取消不计入配额。重建索引 SHALL 按账号去重。

#### Scenario: 同一账号并发提交
- **WHEN** 活跃任务达到配置上限，或请求额度耗尽
- **THEN** 新请求被拒绝，不入队且额度拒绝不继续增加计数

### Requirement: 删除会话清理关联状态
新对话和过期清理 SHALL 删除对应Run的检查点和缓存，不删除其他会话的数据。

#### Scenario: 会话过期
- **WHEN** 清理已过期线程
- **THEN** 关联检查点与摘要缓存被移除，其他账号状态保持
