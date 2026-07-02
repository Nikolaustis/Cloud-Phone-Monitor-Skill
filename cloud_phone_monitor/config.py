from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class Target:
    platform: str
    url: str
    fallback_urls: List[str] = field(default_factory=list)


@dataclass
class MonitorConfig:
    timezone: str = "Asia/Shanghai"
    browser_timeout_ms: int = 45_000
    wait_after_load_ms: int = 2_500
    safe_interactions: bool = True
    headless: bool = True
    output_dir: Path | None = None
    platforms: List[str] | None = None
    storage_state: Path | None = None
    save_storage_state: Path | None = None
    login_wait_seconds: int = 0
    targets: Dict[str, Target] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "MonitorConfig":
        return cls(
            targets={
                "VSPhone": Target(
                    platform="VSPhone",
                    url="https://cloud.vsphone.com/buy",
                    fallback_urls=[
                        "https://cloud.vsphone.com/vsphone/doc/en/system/billing.html"
                    ],
                ),
                "Redfinger": Target(
                    platform="Redfinger",
                    url=(
                        "https://www.cloudemulator.net/app/buy"
                        "?utm_source=buying-guide&utm_medium=btn&utm_campaign=buy-btn&channelCode=web"
                    ),
                ),
                "LDCloud": Target(
                    platform="LDCloud",
                    url="https://www.ldcloud.net/web/mobile/buy",
                ),
                "UgPhone": Target(
                    platform="UgPhone",
                    url="https://www.ugphone.com/toc-portal/#/purchaseDevice",
                ),
            }
        )

    def selected_targets(self) -> Dict[str, Target]:
        if not self.platforms:
            return self.targets
        wanted = {p.lower() for p in self.platforms}
        return {name: target for name, target in self.targets.items() if name.lower() in wanted}
