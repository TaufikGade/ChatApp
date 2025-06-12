import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socket
import json
import threading
import time
from datetime import datetime

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("聊天系统")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # 网络相关
        self.socket = None
        self.username = None
        self.running = False
        self.logged_in = False
        
        # 用户列表相关
        self.online_users = set()  # Store online users as a set for faster lookup
        self.registered_users = [] # Store all registered users
        
        # GUI相关
        self.setup_styles()
        self.create_login_frame()
        self.create_main_frame()
        
        # 默认显示登录界面
        self.show_login_frame()
        
        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_styles(self):
        """设置样式"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # 配置样式
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Send.TButton', font=('Arial', 10, 'bold'))
        
       

    def create_login_frame(self):
        """创建登录界面"""
        self.login_frame = ttk.Frame(self.root)
        
        # 标题
        title_label = ttk.Label(self.login_frame, text="聊天系统", style='Title.TLabel')
        title_label.pack(pady=30)
        
        # 登录表单
        form_frame = ttk.Frame(self.login_frame)
        form_frame.pack(pady=20)
        
        # 用户名
        ttk.Label(form_frame, text="用户名:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.username_entry = ttk.Entry(form_frame, width=20, font=('Arial', 10))
        self.username_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # 密码
        ttk.Label(form_frame, text="密码:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.password_entry = ttk.Entry(form_frame, width=20, show='*', font=('Arial', 10))
        self.password_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # 按钮
        button_frame = ttk.Frame(self.login_frame)
        button_frame.pack(pady=20)
        
        self.login_btn = ttk.Button(button_frame, text="登录", command=self.login)
        self.login_btn.pack(side='left', padx=5)
        
        self.register_btn = ttk.Button(button_frame, text="注册", command=self.register)
        self.register_btn.pack(side='left', padx=5)
        
        # 连接状态
        self.connection_label = ttk.Label(self.login_frame, text="未连接", foreground='red')
        self.connection_label.pack(pady=10)
        
        # 绑定回车键
        self.username_entry.bind('<Return>', lambda e: self.password_entry.focus())
        self.password_entry.bind('<Return>', lambda e: self.login())
        
        # 自动连接服务器
        self.connect_to_server()
    
    def create_main_frame(self):
        """创建主聊天界面"""
        self.main_frame = ttk.Frame(self.root)
        
        # 顶部工具栏
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        # 用户信息
        self.user_info_label = ttk.Label(toolbar, text="", style='Header.TLabel')
        self.user_info_label.pack(side='left')
        
        # 登出按钮
        logout_btn = ttk.Button(toolbar, text="登出", command=self.logout)
        logout_btn.pack(side='right')
        
        # 主要内容区域
        main_paned = ttk.PanedWindow(self.main_frame, orient='horizontal')
        main_paned.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 左侧面板 - 功能区
        left_panel = ttk.Frame(main_paned)
        main_paned.add(left_panel, weight=1)
        
        # 群组管理
        group_frame = ttk.LabelFrame(left_panel, text="群组管理", padding=5)
        group_frame.pack(fill='x', pady=5)
        
        ttk.Button(group_frame, text="创建群组", command=self.show_create_group_dialog).pack(fill='x', pady=2)
        ttk.Button(group_frame, text="加入群组", command=self.show_join_group_dialog).pack(fill='x', pady=2)
        ttk.Button(group_frame, text="刷新群组列表", command=self.refresh_groups).pack(fill='x', pady=2)
        
        # 所有用户列表 (包括在线和离线)
        users_frame = ttk.LabelFrame(left_panel, text="所有用户", padding=5)
        users_frame.pack(fill='both', expand=True, pady=5)
        
        self.users_listbox = tk.Listbox(users_frame, height=10)
        self.users_listbox.pack(fill='both', expand=True)
        self.users_listbox.bind('<Double-1>', self.start_private_chat)
        
        # Add tags for coloring (handled in update_users_list with itemconfig)

        # 群组列表
        groups_frame = ttk.LabelFrame(left_panel, text="我的群组", padding=5)
        groups_frame.pack(fill='both', expand=True, pady=5)
        
        self.groups_listbox = tk.Listbox(groups_frame, height=6)
        self.groups_listbox.pack(fill='both', expand=True)
        self.groups_listbox.bind('<Double-1>', self.start_group_chat)
        
        # 右侧面板 - 聊天区域
        right_panel = ttk.Frame(main_paned)
        main_paned.add(right_panel, weight=3)
        
        # 聊天标题
        self.chat_title_label = ttk.Label(right_panel, text="请选择聊天对象", style='Header.TLabel')
        self.chat_title_label.pack(pady=5)
        
        # 聊天记录区域
        chat_frame = ttk.Frame(right_panel)
        chat_frame.pack(fill='both', expand=True, pady=5)
        
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, 
            wrap='word', 
            state='disabled',
            font=('Arial', 10),
            bg='#f0f0f0'
        )
        self.chat_display.pack(fill='both', expand=True)

        self.chat_display.tag_config('offline_user', foreground='gray')
        self.chat_display.tag_config('online_user', foreground='black')
        # 消息输入区域
        input_frame = ttk.Frame(right_panel)
        input_frame.pack(fill='x', pady=5)
        
        self.message_entry = tk.Text(input_frame, height=3, font=('Arial', 10))
        self.message_entry.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        send_btn = ttk.Button(input_frame, text="发送", style='Send.TButton', command=self.send_message)
        send_btn.pack(side='right')
        
        # 绑定发送快捷键
        self.message_entry.bind('<Control-Return>', lambda e: self.send_message())
        
        # 当前聊天信息
        self.current_chat_type = None  # 'private' or 'group'
        self.current_chat_target = None  # 用户名或群组名
    
    def show_login_frame(self):
        """显示登录界面"""
        self.main_frame.pack_forget()
        self.login_frame.pack(fill='both', expand=True)
        self.username_entry.focus()
    
    def show_main_frame(self):
        """显示主界面"""
        self.login_frame.pack_forget()
        self.main_frame.pack(fill='both', expand=True)
        self.user_info_label.config(text=f"欢迎, {self.username}")
        self.refresh_groups()
    
    def connect_to_server(self):
        """连接到服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(('127.0.0.1', 50000))
            self.running = True
            self.connection_label.config(text="已连接", foreground='green')
            
            # 启动消息监听线程
            listener_thread = threading.Thread(target=self.message_listener)
            listener_thread.daemon = True
            listener_thread.start()
            
            return True
        except Exception as e:
            self.connection_label.config(text=f"连接失败: {e}", foreground='red')
            messagebox.showerror("连接错误", f"无法连接到服务器: {e}")
            return False
    
    def send_message_to_server(self, message_dict):
        """发送消息到服务器"""
        try:
            message = json.dumps(message_dict, ensure_ascii=False)
            msg_bytes = message.encode('utf-8')
            length = len(msg_bytes)
            length_bytes = length.to_bytes(4, byteorder='big')
            
            if self.socket is not None:
                self.socket.send(length_bytes + msg_bytes)
                return True
            else:
                messagebox.showerror("发送错误", "未连接到服务器，无法发送消息。")
                return False
        except Exception as e:
            messagebox.showerror("发送错误", f"发送消息失败: {e}")
            return False
    
    def receive_message_from_server(self):
        """接收服务器消息"""
        try:
            # 先读取4字节的长度信息
            if self.socket is None:
                return None
            length_bytes = self.socket.recv(4)
            if not length_bytes:
                return None
            
            length = int.from_bytes(length_bytes, byteorder='big')
            
            # 根据长度读取完整消息
            message_bytes = b''
            while len(message_bytes) < length:
                chunk = self.socket.recv(length - len(message_bytes))
                if not chunk:
                    return None
                message_bytes += chunk
            
            return json.loads(message_bytes.decode('utf-8'))
        except Exception as e:
            print(f"接收消息失败: {e}")
            return None
    
    def message_listener(self):
        """消息监听线程"""
        while self.running:
            try:
                message = self.receive_message_from_server()
                if not message:
                    break
                
                # 在主线程中处理消息
                self.root.after(0, self.handle_received_message, message)
                
            except Exception as e:
                print(f"消息监听出错: {e}")
                break
    
    def handle_received_message(self, message):
        """处理接收到的消息"""
        msg_type = message.get("type", "")
        
        if msg_type.endswith("_response"):
            self.handle_response_message(message)
        elif msg_type == "private_message":
            self.handle_private_message(message)
        elif msg_type == "group_message":
            self.handle_group_message(message)
        elif msg_type == "update_online_users":
            # Assuming 'update_online_users' also includes 'registered_users' now
            self.online_users = set(message.get("data", {}).get("online_users", []))
            self.registered_users = message.get("data", {}).get("registered_users", [])
            self.update_users_list()
    
    def handle_response_message(self, message):
        """处理服务器响应"""
        msg_type = message.get("type", "")
        status = message.get("status", "")
        msg_text = message.get("message", "")
        data = message.get("data", {})
        
        if msg_type == "login_response":
            if status == "success":
                self.logged_in = True
                self.show_main_frame()
                
                # Update online and registered users
                self.online_users = set(data.get("online_users", []))
                self.registered_users = data.get("registered_users", [])
                self.update_users_list()
            else:
                messagebox.showerror("登录失败", msg_text)
                
        elif msg_type == "register_response":
            if status == "success":
                messagebox.showinfo("注册成功", msg_text)
            else:
                messagebox.showerror("注册失败", msg_text)
                
        elif msg_type == "list_groups_response":
            if status == "success":
                my_groups = data.get("my_groups", [])
                self.update_groups_list(my_groups)
                
        elif status == "success":
            self.add_system_message(f"✓ {msg_text}")
        else:
            self.add_system_message(f"✗ {msg_text}")
    
    def handle_private_message(self, message):
        """处理私聊消息"""
        data = message.get("data", {})
        sender = data.get("from", "")
        msg_text = data.get("message", "")
        
        # 如果当前正在与发送者聊天，显示消息
        if self.current_chat_type == "private" and self.current_chat_target == sender:
            self.add_chat_message(sender, msg_text, is_incoming=True)
        else:
            # 否则显示通知
            self.add_system_message(f"💬 来自 {sender} 的私聊: {msg_text}")
    
    def handle_group_message(self, message):
        """处理群聊消息"""
        data = message.get("data", {})
        sender = data.get("from", "")
        group = data.get("group", "")
        msg_text = data.get("message", "")
        
        # 如果当前正在群聊中，显示消息
        if self.current_chat_type == "group" and self.current_chat_target == group:
            self.add_chat_message(f"{sender}@{group}", msg_text, is_incoming=True)
        else:
            # 否则显示通知
            self.add_system_message(f"👥 群聊 {group} - {sender}: {msg_text}")
    
    def update_users_list(self):
        """更新所有用户列表，并根据在线状态着色"""
        self.users_listbox.delete(0, tk.END)
        for user in sorted(self.registered_users): # Sort for consistent display
            if user != self.username:  # Don't show self
                if user in self.online_users:
                    self.users_listbox.insert(tk.END, user)
                    self.users_listbox.itemconfig(tk.END, {'fg': 'black'})
                else:
                    self.users_listbox.insert(tk.END, user)
                    self.users_listbox.itemconfig(tk.END, {'fg': 'gray'})
    
    def update_groups_list(self, groups):
        """更新群组列表"""
        self.groups_listbox.delete(0, tk.END)
        for group in groups:
            self.groups_listbox.insert(tk.END, group)
    
    def add_chat_message(self, sender, message, is_incoming=False):
        """添加聊天消息"""
        self.chat_display.config(state='normal')
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if is_incoming:
            self.chat_display.insert(tk.END, f"[{timestamp}] {sender}: {message}\n")
        else:
            self.chat_display.insert(tk.END, f"[{timestamp}] 我: {message}\n")
        
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)
    
    def add_system_message(self, message):
        """添加系统消息"""
        self.chat_display.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_display.insert(tk.END, f"[{timestamp}] 系统: {message}\n")
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)
    
    def clear_chat_display(self):
        """清空聊天显示"""
        self.chat_display.config(state='normal')
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state='disabled')
    
    def login(self):
        """登录"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username or not password:
            messagebox.showerror("输入错误", "用户名和密码不能为空")
            return
        
        self.username = username
        
        message = {
            "type": "login",
            "data": {
                "username": username,
                "password": password
            }
        }
        
        self.send_message_to_server(message)
    
    def register(self):
        """注册"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username or not password:
            messagebox.showerror("输入错误", "用户名和密码不能为空")
            return
        
        message = {
            "type": "register",
            "data": {
                "username": username,
                "password": password
            }
        }
        
        self.send_message_to_server(message)
    
    def logout(self):
        """登出"""
        if self.logged_in:
            # 通知服务器登出
            message = {
                "type": "logout",
                "data": {}
            }
            self.send_message_to_server(message)
        
        self.logged_in = False
        self.username = None
        self.current_chat_type = None
        self.current_chat_target = None
        self.clear_chat_display()
        self.show_login_frame()
        
        # Clear input fields
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)

    def start_private_chat(self, event):
        """开始私聊"""
        selection = self.users_listbox.curselection()
        if selection:
            target_user = self.users_listbox.get(selection[0])
            if target_user == self.username:
                messagebox.showinfo("提示", "不能和自己聊天。")
                return
            
            if target_user not in self.online_users:
                response = messagebox.askyesno("离线用户", f"用户 '{target_user}' 当前不在线。是否仍然发送离线消息？")
                if not response:
                    return

            self.current_chat_type = "private"
            self.current_chat_target = target_user
            self.chat_title_label.config(text=f"私聊 - {target_user}")
            self.clear_chat_display()
            self.message_entry.focus()
    
    def start_group_chat(self, event):
        """开始群聊"""
        selection = self.groups_listbox.curselection()
        if selection:
            target_group = self.groups_listbox.get(selection[0])
            self.current_chat_type = "group"
            self.current_chat_target = target_group
            self.chat_title_label.config(text=f"群聊 - {target_group}")
            self.clear_chat_display()
            self.message_entry.focus()
    
    def send_message(self):
        """发送消息"""
        if not self.logged_in:
            messagebox.showerror("错误", "请先登录")
            return
        
        if not self.current_chat_type or not self.current_chat_target:
            messagebox.showerror("错误", "请先选择聊天对象")
            return
        
        message_text = self.message_entry.get(1.0, tk.END).strip()
        if not message_text:
            return
        
        # 构造消息
        if self.current_chat_type == "private":
            message = {
                "type": "private_chat",
                "data": {
                    "to": self.current_chat_target,
                    "message": message_text
                }
            }
        else:  # group
            message = {
                "type": "group_chat",
                "data": {
                    "group": self.current_chat_target,
                    "message": message_text
                }
            }
        
        # 发送消息
        if self.send_message_to_server(message):
            # 显示自己发送的消息
            self.add_chat_message("", message_text, is_incoming=False)
            # 清空输入框
            self.message_entry.delete(1.0, tk.END)
    
    def show_create_group_dialog(self):
        """显示创建群组对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("创建群组")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        
        # 使对话框模态
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="群组名:").pack(pady=10)
        group_entry = ttk.Entry(dialog, width=30)
        group_entry.pack(pady=5)
        
        def create_group():
            group_name = group_entry.get().strip()
            if not group_name:
                messagebox.showerror("错误", "群组名不能为空")
                return
            
            message = {
                "type": "create_group",
                "data": {
                    "group_name": group_name
                }
            }
            
            self.send_message_to_server(message)
            dialog.destroy()
        
        ttk.Button(dialog, text="创建", command=create_group).pack(pady=10)
        group_entry.focus()
        group_entry.bind('<Return>', lambda e: create_group())
    
    def show_join_group_dialog(self):
        """显示加入群组对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("加入群组")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        
        # 使对话框模态
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="群组名:").pack(pady=10)
        group_entry = ttk.Entry(dialog, width=30)
        group_entry.pack(pady=5)
        
        def join_group():
            group_name = group_entry.get().strip()
            if not group_name:
                messagebox.showerror("错误", "群组名不能为空")
                return
            
            message = {
                "type": "join_group",
                "data": {
                    "group_name": group_name
                }
            }
            
            self.send_message_to_server(message)
            dialog.destroy()
        
        ttk.Button(dialog, text="加入", command=join_group).pack(pady=10)
        group_entry.focus()
        group_entry.bind('<Return>', lambda e: join_group())
    
    def refresh_groups(self):
        """刷新群组列表"""
        if self.logged_in:
            message = {
                "type": "list_groups",
                "data": {}
            }
            self.send_message_to_server(message)
    
    def on_closing(self):
        """关闭程序"""
        self.running = False
        if self.socket:
            self.socket.close()
        self.root.destroy()
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()

def main():
    app = ChatGUI()
    app.run()

if __name__ == "__main__":
    main()