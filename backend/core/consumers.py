import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class TenantConsumer(AsyncJsonWebsocketConsumer):
    @database_sync_to_async
    def get_profile_scope(self):
        profile = self.scope["user"].profile
        return profile.organization_id

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        try:
            organization_id = await self.get_profile_scope()
        except (AttributeError, TypeError):
            await self.close(code=4401)
            return
        self.group_name = f"tenant-{organization_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def approval_update(self, event):
        await self.send_json({
            "type": "approval.updated", "project_id": event["project_id"],
            "status": event["status"], "version": event["version"],
        })
