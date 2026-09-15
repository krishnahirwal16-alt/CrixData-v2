import os


class AppConfig:
    def __init__(
        self,
        port: str,
        cache_seconds: int,
        timezone: str,
        highlightly_api_key: str,
        highlightly_base_url: str,
        cricketdata_api_key: str,
        cricketdata_base_url: str,
        sync_admin_token: str,
    ):
        self.port = port
        self.cache_seconds = cache_seconds
        self.timezone = timezone

        self.highlightly_api_key = (
            highlightly_api_key
        )

        self.highlightly_base_url = (
            highlightly_base_url
        )

        self.cricketdata_api_key = (
            cricketdata_api_key
        )

        self.cricketdata_base_url = (
            cricketdata_base_url
        )

        self.sync_admin_token = (
            sync_admin_token
        )

    @classmethod
    def from_env(cls):
        return cls(
            port=os.getenv(
                "PORT",
                "10000",
            ),

            cache_seconds=int(
                os.getenv(
                    "CRIXDATA_CACHE_SECONDS",
                    "900",
                )
            ),

            timezone=os.getenv(
                "CRIXDATA_TIMEZONE",
                "Asia/Kolkata",
            ),

            highlightly_api_key=os.getenv(
                "HIGHLIGHTLY_API_KEY",
                "",
            ),

            highlightly_base_url=os.getenv(
                "HIGHLIGHTLY_BASE_URL",
                "https://cricket.highlightly.net",
            ),

            cricketdata_api_key=os.getenv(
                "CRICKET_API_KEY",
                "",
            ),

            cricketdata_base_url=os.getenv(
                "CRICKETDATA_BASE_URL",
                "https://api.cricapi.com/v1",
            ),

            sync_admin_token=os.getenv(
                "SYNC_ADMIN_TOKEN",
                "",
            ),
        )
