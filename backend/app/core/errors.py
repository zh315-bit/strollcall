class ProviderError(Exception):
    """An external provider failed. `code` matches the error states in DEV_DOC section 3."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
