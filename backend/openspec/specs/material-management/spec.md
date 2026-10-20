# 材料管理契约

上传 `POST /api/documents/materials` 默认仅保存原文件，单文件不超过 20 MiB，不提取文字、不创建审核项，返回 uploaded 状态。保留显式 recognize=true 的历史识别调用。空文件、超限文件及重复内容沿用服务端校验。

PATCH /api/documents/materials/{id} 支持可选 name、folder_id；省略目录字段时不更改目录，null 表示未分类。文件名去除两端空白，长度 1 至 255，不允许路径分隔符或换行。资源和目标目录均执行所属用户校验。

GET /api/documents/materials/{id}/download 返回 attachment；content 路径保留原文件查看。目录沿用新建、重命名、删除接口；删除目录将文件移至未分类。

Nginx 请求体上限配置为 22 MiB，给 20 MiB 文件的 multipart 表单预留空间。修改配置需部署后生效。

新建同名目录返回 HTTP 409 / FOLDER_DUPLICATE，提示目录名称已存在；并发创建触发唯一约束时回滚事务并返回同样错误，不映射为服务不可用。

GET /api/hub/search 按材料文件名及所属目录名称匹配，目录名称匹配时同时返回目录与目录内材料。结果保持 document / folder kind 兼容，材料 URL 为 /documents?folder={folder_id}#material-{id}（未分类使用空 folder 参数），目录 URL 为 /documents?folder={id}#directory-{id}；通配符按字面转义，按资源所属用户隔离。搜索文件元信息，不读取二进制文件内容。
