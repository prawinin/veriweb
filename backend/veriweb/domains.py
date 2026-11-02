from urllib.parse import urlsplit

from tldextract import TLDExtract

EXTRACT = TLDExtract(cache_dir=None, suffix_list_urls=(), include_psl_private_domains=True)


def publisher_domain(url: str) -> str:
    parts = EXTRACT(url)
    return (
        f"{parts.domain}.{parts.suffix}"
        if parts.suffix
        else (urlsplit(url).hostname or "").removeprefix("www.")
    )
