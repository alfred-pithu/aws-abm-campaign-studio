from pydantic import BaseModel


class AssetRecord(BaseModel):
    asset_id: str
    name: str
    path: str
    approved: bool
    allowed_channels: list[str]
    description: str


class SelectedAsset(BaseModel):
    """Hydrated by code after the Asset Agent returns an asset_id.

    The LLM must never invent `path`.
    """

    asset_id: str
    reason: str
    name: str = ""
    path: str = ""
    approved: bool = False
    source: str = "local asset registry"
