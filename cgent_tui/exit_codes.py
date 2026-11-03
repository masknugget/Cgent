"""Process exit codes, aligned with shell composition conventions.

0    server 明确成功,响应契约有效,output 已输出
1    invocation 失败、非用户中断的取消、连接/协议错误、总期限到期或远端状态未知
2    CLI 用法、配置或输入编码/大小错误
130  本地被 Ctrl-C 中断;不隐含 server 已取消
"""

EX_OK = 0
EX_FAILED = 1
EX_USAGE = 2
EX_INTERRUPTED = 130
