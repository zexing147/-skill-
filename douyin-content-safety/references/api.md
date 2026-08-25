# 抖音文本内容安全接口

线上：`POST https://developer.toutiao.com/api/v2/tags/text/antidirt`

沙盒：`POST https://open-sandbox.douyin.com/api/v2/tags/text/antidirt`

请求头：`X-Token: <小程序 access_token>`、`Content-Type: application/json`

请求体：`{"tasks":[{"content":"要检测的文本"}]}`

响应重点字段：`log_id`、`data[].code`、`data[].msg`、`data[].task_id`、`data[].predicts[].hit`、`data[].predicts[].target`、`data[].predicts[].model_name`、`data[].predicts[].prob`。

错误码：`0` 成功，`400` 参数有误，`401` access_token 校验失败。
