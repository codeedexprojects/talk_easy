import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from django.db import models
from calls.models import AgoraCallHistory
from executives.models import Executive
from users.models import UserProfile


class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            # Get user from middleware (set by JWTAuthMiddleware)
            self.user = self.scope.get("user")
            
            # Check if user is authenticated
            if not self.user or isinstance(self.user, AnonymousUser):
                print("WebSocket: User not authenticated")
                await self.close(code=4001)
                return
            
            print(f"WebSocket: User {self.user.id} attempting to connect")
            
            # Accept the connection
            await self.accept()
            
            # Create user-specific groups
            self.user_group_name = f"user_{self.user.id}"
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            
            # Check if user is an executive
            self.executive_group_name = None
            executive = await self.get_executive_for_user(self.user)
            if executive:
                self.executive_group_name = f"executive_{executive.id}"
                await self.channel_layer.group_add(
                    self.executive_group_name,
                    self.channel_name
                )
                print(f"WebSocket: User {self.user.id} is executive {executive.id}")
            
            # Send connection confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'WebSocket connected successfully!',
                'user_id': self.user.id,
                'executive_id': executive.id if executive else None,
                'timestamp': timezone.now().isoformat(),
                'status': 'connected'
            }))
            
            print(f"WebSocket: Connection established for user {self.user.id}")
            
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close(code=4000)

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected with code: {close_code}")
        
        # Leave groups
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
        
        if hasattr(self, 'executive_group_name') and self.executive_group_name:
            await self.channel_layer.group_discard(
                self.executive_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            if not hasattr(self, 'user') or not self.user:
                await self.send_error("Authentication required")
                await self.close(code=4001)
                return
                
            data = json.loads(text_data)
            message_type = data.get('type')
            
            print(f"Received WebSocket message: {data}")
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat(),
                    'message': 'WebSocket is working perfectly!',
                    'user_id': self.user.id
                }))
                
            elif message_type == 'test_connection':
                await self.send(text_data=json.dumps({
                    'type': 'connection_test_response',
                    'timestamp': timezone.now().isoformat(),
                    'message': 'Connection test successful',
                    'server_status': 'running',
                    'websocket_status': 'connected',
                    'user_authenticated': True,
                    'user_id': self.user.id
                }))
                
            elif message_type == 'call_action':
                await self.handle_call_action(data)
                
            elif message_type == 'heartbeat':
                await self.handle_heartbeat(data)
                
            elif message_type == 'get_user_info':
                executive = await self.get_executive_for_user(self.user)
                await self.send(text_data=json.dumps({
                    'type': 'user_info',
                    'user_id': self.user.id,
                    'mobile_number': getattr(self.user, 'mobile_number', 'N/A'),
                    'is_executive': executive is not None,
                    'executive_id': executive.id if executive else None,
                    'timestamp': timezone.now().isoformat()
                }))
                
            else:
                await self.send_error(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            print(f"Error processing WebSocket message: {e}")
            await self.send_error(f"Error processing message: {str(e)}")

    # Authentication is now handled by middleware

    async def handle_call_action(self, data):
        """Handle call actions like accept, reject, end, etc."""
        action = data.get('action')
        call_id = data.get('call_id')
        
        if not call_id:
            await self.send_error("Call ID is required")
            return
            
        try:
            call = await self.get_user_call(call_id)
            if not call:
                await self.send_error("Call not found or access denied")
                return
                
        except Exception as e:
            await self.send_error(f"Error finding call: {str(e)}")
            return

        if action == 'accept_call':
            await self.accept_call(call)
        elif action == 'reject_call':
            await self.reject_call(call)
        elif action == 'end_call':
            await self.end_call(call)
        elif action == 'cancel_call':
            await self.cancel_call(call)
        elif action == 'join_call':
            await self.join_call(call)
        else:
            await self.send_error(f"Unknown action: {action}")

    async def accept_call(self, call):
        """Executive accepts the call"""
        executive = await self.get_executive_for_user(self.user)
        if not executive or call.executive.id != executive.id:
            await self.send_error("You don't have permission to accept this call")
            return
            
        if call.status != 'pending':
            await self.send_error(f"Call is not in pending state. Current status: {call.status}")
            return
            
        await database_sync_to_async(self.update_call_status)(call, 'ringing')
        
        # Notify caller
        await self.channel_layer.group_send(
            f"user_{call.user.id}",
            {
                'type': 'call_accepted_event',
                'call_id': call.id,
                'executive_token': getattr(call, 'executive_token', ''),
                'callee_uid': getattr(call, 'callee_uid', None)
            }
        )
        
        await self.send(text_data=json.dumps({
            'type': 'action_success',
            'action': 'accept_call',
            'call_id': call.id,
            'status': 'ringing',
            'message': 'Call accepted successfully',
            'timestamp': timezone.now().isoformat()
        }))

    async def reject_call(self, call):
        """Executive rejects the call"""
        executive = await self.get_executive_for_user(self.user)
        if not executive or call.executive.id != executive.id:
            await self.send_error("You don't have permission to reject this call")
            return
            
        if call.status not in ['pending', 'ringing']:
            await self.send_error(f"Call cannot be rejected. Current status: {call.status}")
            return
            
        await database_sync_to_async(self.update_call_status)(call, 'rejected')
        
        if hasattr(call, 'executive'):
            await database_sync_to_async(self.clear_executive_on_call)(call.executive)
        
        # Notify caller
        await self.channel_layer.group_send(
            f"user_{call.user.id}",
            {
                'type': 'call_rejected_event',
                'call_id': call.id
            }
        )
        
        await self.send(text_data=json.dumps({
            'type': 'action_success',
            'action': 'reject_call',
            'call_id': call.id,
            'status': 'rejected',
            'message': 'Call rejected successfully',
            'timestamp': timezone.now().isoformat()
        }))

    async def end_call(self, call):
        """End an active call"""
        user_can_end = await self.user_can_end_call(call)
        if not user_can_end:
            await self.send_error("You don't have permission to end this call")
            return
            
        try:
            await database_sync_to_async(call.end_call)(ender=f"user_{self.user.id}")
            
            if hasattr(call, 'executive'):
                await database_sync_to_async(self.clear_executive_on_call)(call.executive)
            
            # Notify both parties
            await self.channel_layer.group_send(
                f"user_{call.user.id}",
                {
                    'type': 'call_ended_event',
                    'call_id': call.id,
                    'duration': str(call.duration) if hasattr(call, 'duration') and call.duration else None
                }
            )
            
            if hasattr(call, 'executive'):
                await self.channel_layer.group_send(
                    f"executive_{call.executive.id}",
                    {
                        'type': 'call_ended_event',
                        'call_id': call.id,
                        'duration': str(call.duration) if hasattr(call, 'duration') and call.duration else None
                    }
                )
            
            await self.send(text_data=json.dumps({
                'type': 'action_success',
                'action': 'end_call',
                'call_id': call.id,
                'status': 'ended',
                'message': 'Call ended successfully',
                'timestamp': timezone.now().isoformat()
            }))
            
        except Exception as e:
            await self.send_error(f"Error ending call: {str(e)}")

    async def cancel_call(self, call):
        """Cancel a pending call"""
        if call.user.id != self.user.id:
            await self.send_error("You don't have permission to cancel this call")
            return
            
        if call.status not in ['pending', 'ringing']:
            await self.send_error(f"Call cannot be cancelled. Current status: {call.status}")
            return
            
        await database_sync_to_async(self.update_call_status)(call, 'cancelled')
        
        if hasattr(call, 'executive'):
            await database_sync_to_async(self.clear_executive_on_call)(call.executive)
        
        # Notify executive
        if hasattr(call, 'executive'):
            await self.channel_layer.group_send(
                f"executive_{call.executive.id}",
                {
                    'type': 'call_cancelled_event',
                    'call_id': call.id
                }
            )
        
        await self.send(text_data=json.dumps({
            'type': 'action_success',
            'action': 'cancel_call',
            'call_id': call.id,
            'status': 'cancelled',
            'message': 'Call cancelled successfully',
            'timestamp': timezone.now().isoformat()
        }))

    async def join_call(self, call):
        """User joins the call"""
        if call.user.id != self.user.id:
            await self.send_error("You don't have permission to join this call")
            return
            
        try:
            await database_sync_to_async(call.mark_joined)()
            
            if hasattr(call, 'executive'):
                await self.channel_layer.group_send(
                    f"executive_{call.executive.id}",
                    {
                        'type': 'call_joined_event',
                        'call_id': call.id,
                        'joined_at': call.joined_at.isoformat() if hasattr(call, 'joined_at') and call.joined_at else None
                    }
                )
            
            await self.send(text_data=json.dumps({
                'type': 'action_success',
                'action': 'join_call',
                'call_id': call.id,
                'status': 'joined',
                'message': 'Joined call successfully',
                'timestamp': timezone.now().isoformat()
            }))
            
        except Exception as e:
            await self.send_error(f"Error joining call: {str(e)}")

    async def handle_heartbeat(self, data):
        """Handle heartbeat messages"""
        call_id = data.get('call_id')
        if call_id:
            try:
                call = await self.get_user_call(call_id)
                if not call:
                    await self.send_error("Call not found or access denied")
                    return
                    
                if call.is_active and call.status == 'joined':
                    await database_sync_to_async(self.update_heartbeat)(call)
                    
                    await self.send(text_data=json.dumps({
                        'type': 'heartbeat_ack',
                        'call_id': call_id,
                        'timestamp': timezone.now().isoformat(),
                        'message': 'Heartbeat received and processed'
                    }))
                else:
                    await self.send_error("Call is not active or not joined")
            except Exception as e:
                await self.send_error(f"Error processing heartbeat: {str(e)}")

    # Database operations
    @database_sync_to_async
    def get_executive_for_user(self, user):
        """Get executive profile for the authenticated user"""
        try:
            return Executive.objects.filter(manager_executive=user).first()
        except:
            return None

    @database_sync_to_async
    def get_user_call(self, call_id):
        """Get call that belongs to the authenticated user"""
        try:
            executive = Executive.objects.filter(manager_executive=self.user).first()
            
            if executive:
                return AgoraCallHistory.objects.filter(
                    id=call_id
                ).filter(
                    models.Q(user=self.user) | models.Q(executive=executive)
                ).first()
            else:
                return AgoraCallHistory.objects.filter(
                    id=call_id, user=self.user
                ).first()
        except:
            return None

    @database_sync_to_async
    def user_can_end_call(self, call):
        """Check if user can end the call"""
        try:
            if call.user.id == self.user.id:
                return True
                
            executive = Executive.objects.filter(manager_executive=self.user).first()
            if executive and call.executive.id == executive.id:
                return True
                
            return False
        except:
            return False

    @database_sync_to_async
    def update_call_status(self, call, status):
        call.status = status
        call.save(update_fields=['status'])

    @database_sync_to_async
    def clear_executive_on_call(self, executive):
        executive.on_call = False
        executive.save(update_fields=['on_call'])

    @database_sync_to_async
    def update_heartbeat(self, call):
        call.last_heartbeat = timezone.now()
        call.save(update_fields=['last_heartbeat'])

    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat(),
            'status': 'error'
        }))

    # WebSocket event handlers
    async def call_accepted_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_accepted',
            **event
        }))

    async def call_rejected_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_rejected',
            **event
        }))

    async def call_ended_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_ended',
            **event
        }))

    async def call_cancelled_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_cancelled',
            **event
        }))

    async def call_joined_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_joined',
            **event
        }))

    async def call_missed_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_missed',
            **event
        }))

    async def incoming_call(self, event):
        await self.send(text_data=json.dumps({
            'type': 'incoming_call',
            **event
        }))