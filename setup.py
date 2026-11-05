from pathlib import Path
from setuptools import find_packages, setup

ROOT = Path(__file__).parent
setup(
    name="neurodynamic-mcp",
    version="1.1.2",
    description="Audio, captions, documents and LLM APIs for agents with explicitly capped USDC purchases",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://x402.neurodynamic.tech/",
    project_urls={
        "Documentation": "https://x402.neurodynamic.tech/integrations/mcp",
        "Support": "https://neurodynamic.tech/contact",
    },
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["mcp==2.2.0", "httpx==0.28.1", "x402[evm]==2.16.0", "aiohttp>=3.14.4", "certifi>=2026.10.18", "multidict>=6.9.1", "opentelemetry-api>=1.45.1", "PyJWT>=2.15.0", "urllib3>=2.8.0"],
    entry_points={"console_scripts": ["neurodynamic-mcp=neurodynamic_mcp.server:main"]},
)
