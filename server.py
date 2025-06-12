import asyncio
import json
import hashlib
import time
from typing import Dict, Set, Tuple, Optional

# 全局数据存储
online_users: Dict[str, Tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
users_db: Dict[str, dict] = {}  # 用户数据库 {username: {password_hash, created_time}}
groups: Dict[str, Set[str]] = {}  # 群组 {group_name: {user1, user2, ...}}
offline_messages: Dict[str, list] = {}  # 离线消息队列 {username: [message1, message2, ...]}

IP = '127.0.0.1' # Listen on localhost
PORT = 50000
BUFLEN = 4096

def hash_password(password: str) -> str:
    """密码哈希处理"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_response(msg_type: str, status: str = "success", data: Optional[dict] = None, message: str = "") -> str:
    """创建标准响应消息"""
    response = {
        "type": msg_type + "_response",
        "status": status,
        "message": message,
        "timestamp": time.time()
    }
    if data:
        response["data"] = data
    return json.dumps(response, ensure_ascii=False)

def create_notification(msg_type: str, data: dict) -> str:
    """创建通知消息"""
    notification = {
        "type": msg_type,
        "data": data,
        "timestamp": time.time()
    }
    return json.dumps(notification, ensure_ascii=False)

async def send_message(writer: asyncio.StreamWriter, message: str):
    """发送消息到客户端"""
    try:
        # 添加消息长度前缀解决粘包问题
        msg_bytes = message.encode('utf-8')
        length = len(msg_bytes)
        length_bytes = length.to_bytes(4, byteorder='big')
        
        writer.write(length_bytes + msg_bytes)
        await writer.drain()
    except Exception as e:
        print(f"发送消息失败: {e}")

async def receive_message(reader: asyncio.StreamReader) -> str:
    """接收完整消息"""
    try:
        # 先读取4字节的长度信息
        length_bytes = await reader.readexactly(4)
        length = int.from_bytes(length_bytes, byteorder='big')
        
        # 根据长度读取完整消息
        message_bytes = b''
        while len(message_bytes) < length:
            chunk = await reader.read(length - len(message_bytes)) # Use read to avoid blocking if less than expected
            if not chunk:
                # Connection closed prematurely
                raise ConnectionResetError("Client disconnected unexpectedly.")
            message_bytes += chunk
        
        return message_bytes.decode('utf-8')
    except asyncio.IncompleteReadError:
        print("Client disconnected during message reception.")
        return ""
    except Exception as e:
        print(f"接收消息失败: {e}")
        return ""

async def broadcast_online_users_update():
    """向所有在线用户广播更新的在线用户和所有注册用户列表"""
    online_list = list(online_users.keys())
    registered_list = list(users_db.keys()) # Get all registered users

    notification = create_notification(
        "update_online_users",
        {"online_users": online_list, "registered_users": registered_list}
    )
    for _, (_, writer) in online_users.items():
        await send_message(writer, notification)

async def handle_register(data: dict, writer: asyncio.StreamWriter) -> str:
    """处理用户注册"""
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return create_response("register", "error", message="用户名和密码不能为空")
    
    if username in users_db:
        return create_response("register", "error", message="用户名已存在")
    
    # 保存用户信息
    users_db[username] = {
        "password_hash": hash_password(password),
        "created_time": time.time()
    }
    
    print(f"新用户注册: {username}")
    # After registration, update all clients about the new registered user
    await broadcast_online_users_update() 
    return create_response("register", "success", message="注册成功")

async def handle_login(data: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, current_user: list) -> str:
    """处理用户登录"""
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return create_response("login", "error", message="用户名和密码不能为空")
    
    if username not in users_db:
        return create_response("login", "error", message="用户不存在")
    
    if users_db[username]["password_hash"] != hash_password(password):
        return create_response("login", "error", message="密码错误")
    
    if username in online_users:
        return create_response("login", "error", message="用户已在线")
    
    # 登录成功，添加到在线用户列表
    online_users[username] = (reader, writer)
    current_user[0] = username  # 更新当前连接的用户名
    
    print(f"用户登录: {username}")
    
    # 获取在线用户列表和所有注册用户列表
    online_list = list(online_users.keys())
    registered_list = list(users_db.keys())

    # 发送离线消息
    if username in offline_messages:
        for message in offline_messages[username]:
            await send_message(writer, message)
        del offline_messages[username]  # 清空离线消息队列
    
    # Broadcast to all online users about the login
    await broadcast_online_users_update()

    return create_response("login", "success", 
                           data={"online_users": online_list, "registered_users": registered_list}, 
                           message="登录成功")

async def handle_private_chat(data: dict, sender: str) -> str:
    """处理私聊消息"""
    target = data.get("to", "").strip()
    message = data.get("message", "").strip()
    
    if not target or not message:
        return create_response("private_chat", "error", message="目标用户和消息内容不能为空")
    
    if target == sender:
        return create_response("private_chat", "error", message="不能发送消息给自己")
    
    # Check if target user exists in the database
    if target not in users_db:
        return create_response("private_chat", "error", message="目标用户不存在")

    notification = create_notification("private_message", {
        "from": sender,
        "message": message
    })
    
    if target in online_users:
        # 转发消息给目标用户
        target_writer = online_users[target][1]
        await send_message(target_writer, notification)
        return create_response("private_chat", "success", message="消息已发送")
    else:
        # 存储离线消息
        if target not in offline_messages:
            offline_messages[target] = []
        offline_messages[target].append(notification)
        return create_response("private_chat", "success", message="目标用户不在线，消息已存储为离线消息")
        
async def handle_group_chat(data: dict, sender: str) -> str:
    """处理群聊消息"""
    group_name = data.get("group", "").strip()
    message = data.get("message", "").strip()
    
    if not group_name or not message:
        return create_response("group_chat", "error", message="群名和消息内容不能为空")
    
    if group_name not in groups:
        return create_response("group_chat", "error", message="群组不存在")
    
    if sender not in groups[group_name]:
        return create_response("group_chat", "error", message="您不在该群组中")
    
    # 广播消息给群组中的所有在线用户（除了发送者）
    notification = create_notification("group_message", {
        "from": sender,
        "group": group_name,
        "message": message
    })
    
    sent_count = 0
    for member in groups[group_name]:
        if member != sender and member in online_users:
            member_writer = online_users[member][1]
            await send_message(member_writer, notification)
            sent_count += 1
    
    return create_response("group_chat", "success", 
                           data={"sent_to": sent_count}, 
                           message="消息已发送")

async def handle_create_group(data: dict, creator: str) -> str:
    """处理创建群组"""
    group_name = data.get("group_name", "").strip()
    
    if not group_name:
        return create_response("create_group", "error", message="群组名不能为空")
    
    if group_name in groups:
        return create_response("create_group", "error", message="群组已存在")
    
    # 创建群组，创建者自动加入
    groups[group_name] = {creator}
    
    print(f"用户 {creator} 创建了群组: {group_name}")
    return create_response("create_group", "success", message="群组创建成功")

async def handle_join_group(data: dict, user: str) -> str:
    """处理加入群组"""
    group_name = data.get("group_name", "").strip()
    
    if not group_name:
        return create_response("join_group", "error", message="群组名不能为空")
    
    if group_name not in groups:
        return create_response("join_group", "error", message="群组不存在")
    
    if user in groups[group_name]:
        return create_response("join_group", "error", message="您已在该群组中")
    
    # 加入群组
    groups[group_name].add(user)
    
    print(f"用户 {user} 加入了群组: {group_name}")
    return create_response("join_group", "success", message="成功加入群组")

async def handle_list_groups(data: dict, user: str) -> str:
    """处理获取群组列表"""
    user_groups = [group_name for group_name, members in groups.items() if user in members]
    all_groups = list(groups.keys())
    
    return create_response("list_groups", "success", 
                           data={
                               "my_groups": user_groups,
                               "all_groups": all_groups
                           })

async def handle_logout(user: str):
    """处理用户登出"""
    if user in online_users:
        del online_users[user]
        print(f"用户 {user} 已登出")
        
        # 广播在线用户列表更新 (including all registered users)
        await broadcast_online_users_update()

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """处理客户端连接"""
    addr = writer.get_extra_info('peername')
    current_user = [None]  # 使用列表来存储当前用户名，便于在函数间传递
    
    print(f'客户端 {addr} 连接成功')
    
    try:
        while True:
            # 接收消息
            raw_message = await receive_message(reader)
            if not raw_message: # Client disconnected or error
                break
            
            try:
                # 解析JSON消息
                message = json.loads(raw_message)
                msg_type = message.get("type", "")
                data = message.get("data", {})
                
                print(f'收到来自 {addr} 的消息: {message}')
                
                response = ""
                
                # 根据消息类型处理
                if msg_type == "register":
                    response = await handle_register(data, writer)
                    
                elif msg_type == "login":
                    response = await handle_login(data, reader, writer, current_user)
                    
                elif msg_type == "logout":
                    if current_user[0]:
                        await handle_logout(current_user[0])
                        current_user[0] = None # Reset current user after logout
                        response = create_response("logout", "success", message="已成功登出")
                    else:
                        response = create_response("logout", "error", message="您尚未登录")
                        
                elif current_user[0]:  # 需要登录后才能使用的功能
                    if msg_type == "private_chat":
                        response = await handle_private_chat(data, current_user[0])
                    elif msg_type == "group_chat":
                        response = await handle_group_chat(data, current_user[0])
                    elif msg_type == "create_group":
                        response = await handle_create_group(data, current_user[0])
                    elif msg_type == "join_group":
                        response = await handle_join_group(data, current_user[0])
                    elif msg_type == "list_groups":
                        response = await handle_list_groups(data, current_user[0])
                    else:
                        response = create_response("unknown", "error", message="未知的消息类型")
                else:
                    response = create_response("auth", "error", message="请先登录")
                
                # 发送响应
                if response:
                    await send_message(writer, response)
                    
            except json.JSONDecodeError:
                error_response = create_response("parse", "error", message="消息格式错误")
                await send_message(writer, error_response)
            except Exception as e:
                print(f"处理消息时出错: {e}")
                error_response = create_response("server", "error", message="服务器内部错误")
                await send_message(writer, error_response)
                
    except (ConnectionResetError, asyncio.IncompleteReadError):
        print(f"客户端 {addr} 断开连接。")
    except Exception as e:
        print(f"连接 {addr} 出现错误: {e}")
    finally:
        # 清理用户连接
        if current_user[0] and current_user[0] in online_users:
            await handle_logout(current_user[0]) # Ensure logout handling
        
        print(f'客户端 {addr} 断开连接')
        writer.close()

async def main():
    """主函数"""
    server = await asyncio.start_server(handle_client, IP, PORT)
    
    print(f'聊天服务器启动成功，监听端口 {PORT}')
    print('支持的功能: 用户注册、登录、私聊、群聊')
    print('按 Ctrl+C 退出服务器')
    
    try:
        await server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器正在关闭...')
    finally:
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    # Pre-populate some users for testing
    #users_db['user1'] = {'password_hash': hash_password('pass1'), 'created_time': time.time()}
    #users_db['user2'] = {'password_hash': hash_password('pass2'), 'created_time': time.time()}
    #users_db['user3'] = {'password_hash': hash_password('pass3'), 'created_time': time.time()}
    
    asyncio.run(main())