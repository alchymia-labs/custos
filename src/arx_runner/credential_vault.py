"""ExchangeCredential 本地金库（sops+age / Vault）。KEK 不出本地，permission_scope 禁提币。

解密 = 必写 AuditLog(CredentialDecrypted)。产品面（云端）schema 永不持有 Key。
"""
