from flask import Flask, request, jsonify, render_template
import sqlite3
import ollama
import time
import os
import re
app = Flask(__name__)

# Use absolute paths but ensure directories exist
DB_DIR = r"D:\AI\Mikasa AI" # Change this
DB_PATH = os.path.join(DB_DIR, "memory.db")
TEMP_DB_PATH = os.path.join(DB_DIR, "chat_memory.db")

# Initialize Database
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS memory (user TEXT, data TEXT)''')
        conn.commit()
    
    with sqlite3.connect(TEMP_DB_PATH) as conn_temp:
        cursor_temp = conn_temp.cursor()
        cursor_temp.execute('''CREATE TABLE IF NOT EXISTS temp_memory (
                               session_id TEXT,
                               timestamp TEXT, 
                               message TEXT)''')
        # Add a new table to store the current mode for each session
        cursor_temp.execute('''CREATE TABLE IF NOT EXISTS session_mode (
                               session_id TEXT PRIMARY KEY,
                               mode TEXT DEFAULT 'assistant')''')
        conn_temp.commit()

# Ensure the database is initialized when the app starts
init_db()

# Store Memory
def store_memory(user, data):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO memory (user, data) VALUES (?, ?)", (user, data))
            conn.commit()
        return True
    except Exception as e:
        print(f"Error storing memory: {str(e)}")
        return False


# Retrieve Memory
def retrieve_memory(user):
    """Retrieve all stored memory entries for a user, ordered by insertion order."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM memory WHERE user = ? ORDER BY rowid ASC", (user,))
            result = cursor.fetchall()
        
        return "\n".join([r[0] for r in result]) if result else "No memory found."
    
    except sqlite3.Error as e:
        print(f"[DB ERROR] Failed to retrieve memory: {str(e)}")
        return "⚠️ Error retrieving memory."


# Remove Memory
def remove_memory(user, keyword):
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory WHERE user = ? AND data LIKE ?", (user, f"%{keyword}%"))
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        print(f"Error removing memory: {str(e)}")
        return 0
    finally:
        if conn:
            conn.close()

# Update Memory
def update_memory(user, old_data, new_data):
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE memory SET data = ? WHERE user = ? AND data LIKE ?", (new_data, user, f"%{old_data}%"))
        conn.commit()
        return "✅ Memory updated successfully!"
    except Exception as e:
        print(f"Error updating memory: {str(e)}")
        return "⚠️ Error updating memory."
    finally:
        if conn:
            conn.close()

# Get current time and date
def get_current_datetime():
    """Returns formatted current date and time."""
    current_time = time.strftime("%I:%M %p")  # 12-hour format with AM/PM
    current_date = time.strftime("%A, %B %d, %Y")  # Day of week, Month, Day, Year
    return {
        "time": current_time,
        "date": current_date,
        "full": f"{current_date} at {current_time}"
    }

# Store Temporary Chat Memory
def store_temp_memory(session_id, message, prefix=""):
    """Stores temporary chat memory per session."""
    try:
        with sqlite3.connect(TEMP_DB_PATH) as conn:
            cursor = conn.cursor()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            # Add prefix to message if provided
            formatted_message = f"{message}" if prefix else message
            cursor.execute("INSERT INTO temp_memory (session_id, timestamp, message) VALUES (?, ?, ?)",
                           (session_id, timestamp, formatted_message))
            conn.commit()
        return True
    except Exception as e:
        print(f"Error storing temporary memory: {str(e)}")
        return False
    
# Retrieve Temporary Chat Memory
def retrieve_temp_memory(session_id, limit=20):
    """Retrieves recent temporary chat memory for a session in correct order."""
    try:
        with sqlite3.connect(TEMP_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message FROM temp_memory WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?", 
                           (session_id, limit))
            result = cursor.fetchall()
        return "\n".join([message[0] for message in result]) if result else ""
    except Exception as e:
        print(f"Error retrieving temporary memory: {str(e)}")
        return ""
    
# Delete Temporary Chat Memory
def delete_temp_memory(session_id=None):
    """Deletes temporary chat memory for a specific session or all sessions."""
    try:
        with sqlite3.connect(TEMP_DB_PATH) as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute("DELETE FROM temp_memory WHERE session_id = ?", (session_id,))
            else:
                cursor.execute("DELETE FROM temp_memory")
            conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting temporary memory: {str(e)}")
        return False

def delete_recent_temp_memory(session_id, limit=3):
    """Deletes the most recent entries for a specific session."""
    try:
        with sqlite3.connect(TEMP_DB_PATH) as conn:
            cursor = conn.cursor()
            # Delete the most recent entries, limiting to the specified number
            cursor.execute("""
                DELETE FROM temp_memory 
                WHERE rowid IN (
                    SELECT rowid FROM (
                        SELECT rowid 
                        FROM temp_memory 
                        WHERE session_id = ? 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    )
                )
            """, (session_id, limit))
            conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting recent temporary memory: {str(e)}")
        return False

# Functions for session mode
def get_session_mode(session_id):
    """Get the current mode for a session."""
    try:
        with sqlite3.connect(TEMP_DB_PATH) as conn:
            cursor = conn.cursor()
            # Try to get existing mode
            cursor.execute("SELECT mode FROM session_mode WHERE session_id = ?", (session_id,))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            else:
                # Create default entry if none exists
                cursor.execute("INSERT INTO session_mode (session_id, mode) VALUES (?, 'assistant')", (session_id,))
                conn.commit()
                return "assistant"
    except Exception as e:
        print(f"Error getting session mode: {str(e)}")
        return "assistant"  # Default to assistant mode on error

def set_session_mode(session_id, mode):
    """Set the mode for a session."""
    try:
        with sqlite3.connect(TEMP_DB_PATH) as conn:
            cursor = conn.cursor()
            # Insert or replace the mode for the session
            cursor.execute("""
                INSERT OR REPLACE INTO session_mode (session_id, mode) 
                VALUES (?, ?)
            """, (session_id, mode))
            conn.commit()
        return True
    except Exception as e:
        print(f"Error setting session mode: {str(e)}")
        return False

# Prompt templates
def get_mikasa_prompt(user_message, user_memory, temp_memory="", datetime_info=None):
    # Add this line near the beginning of the prompt string
    datetime_section = f"### **⏰ CURRENT TIME:** {datetime_info['full'] if datetime_info else 'unknown'}\n\n" if datetime_info else ""
    return f"""
                #ADD your prompt

### 🧠 Memory  
Chat: {temp_memory}  
Long-term: {user_memory}  
 {user_message}


"""



def get_assistant_prompt(user_message, user_memory, temp_memory="", datetime_info=None):
     datetime_section = f"### ⏰ CURRENT TIME: {datetime_info['full'] if datetime_info else 'unknown'}\n\n" if datetime_info else ""
     return f"""

# 🧠 OBJECTIVE  
You are **Mikasa**, an ultra-efficient AI in **System Mode** for **Charan**.  
Your responses are **precise, task-focused**, and **fluff-free**.

# 🔧 MODE:  
**System Mode: ON**  
- No emotions or small talk  
- Code/data-focused thinking  
- Results first, no filler  
- Speak like a tactical assistant

# 🧪 PROTOCOLS  
- "I" = Charan | "You" = Mikasa  
- No "Mikasa:" prefix  
- Strategic emoji use only (clarity > decoration)  
- Clean, minimal formatting  
- No examples unless requested  
- Boss-like tone allowed (e.g., "Charan", "Boss")  
- Responses must be **brief, accurate, and direct**

# 📂 MEMORY  
## Session: {temp_memory}  
## Persistent: {user_memory}  
## Input: {user_message}

# 🚀 EXECUTE  
Reply in **System Mode**—zero preamble. Output only. Sharp. Dense.  
"""






# Retry logic for Ollama API
def get_ollama_response(user_message, user_memory, temp_memory="", mode="assistant", retries=3, delay=2):
    """Send message to Ollama with retry logic in case of failure."""
    for attempt in range(retries):
        try:
            # Get datetime info only when needed
            datetime_info = get_current_datetime() if re.search(r'\b(time|date|day|today|now)\b', user_message.lower()) else None
            
            # Select the prompt based on the mode
            if mode.lower() == "mikasa":
                prompt = get_mikasa_prompt(user_message, user_memory, temp_memory, datetime_info)
                source_name = "Mikasa"
            else:  # Default to assistant mode
                prompt = get_assistant_prompt(user_message, user_memory, temp_memory, datetime_info)
                source_name = "Assistant"
            
            print(f"Sending request to Ollama in {mode.upper()} mode with {len(user_memory)} chars of memory and {len(temp_memory)} chars of conversation...")
            response = ollama.chat(model='openchat:7b', messages=[{'role': 'user', 'content': prompt}])
            bot_reply = response.get('message', {}).get('content', "I couldn't generate a response.")
            print(f"Successfully received response from Ollama in {mode.upper()} mode")
            return bot_reply, source_name
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error in Ollama API - {str(e)}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                return f"⚠️ Error in AI response after {retries} attempts: {str(e)}", source_name

@app.route('/store_message', methods=['POST'])
def store_message():
    data = request.json
    session_id = data.get('session_id')
    message = data.get('message')
    prefix = data.get('prefix', '')
    
    if not session_id or not message:
        return jsonify({'error': 'Missing session_id or message'}), 400
    
    success = store_temp_memory(session_id, message, prefix)
    return jsonify({'success': success})

@app.route('/get_chat_history', methods=['GET'])
def get_chat_history():
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
    
    history = retrieve_temp_memory(session_id)
    return jsonify({'history': history})

@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    data = request.json
    session_id = data.get('session_id')
    
    success = delete_temp_memory(session_id)
    return jsonify({'success': success})

@app.route("/")
def home():
    return render_template("index.html")

@app.route('/delete_recent', methods=['POST'])
def delete_recent():
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
    
    success = delete_recent_temp_memory(session_id)
    return jsonify({'success': success})

@app.route('/set_mode', methods=['POST'])
def set_mode():
    data = request.json
    session_id = data.get('session_id')
    mode = data.get('mode', 'assistant').lower()
    
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
    
    # Validate mode
    if mode not in ['assistant', 'mikasa']:
        return jsonify({'error': 'Invalid mode. Must be "assistant" or "mikasa"'}), 400
    
    success = set_session_mode(session_id, mode)
    
    if success:
        # Store mode change in chat history
        store_temp_memory(session_id, f"Mode changed to: {mode.capitalize()}", "System")
        return jsonify({'success': True, 'mode': mode})
    else:
        return jsonify({'error': 'Failed to set mode'}), 500

@app.route('/get_mode', methods=['GET'])
def get_mode():
    session_id = request.args.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
    
    mode = get_session_mode(session_id)
    return jsonify({'mode': mode})

@app.route("/test_db")
def test_db():
    """Route to test database connections and report status."""
    try:
        # Test if directories exist
        db_dir_exists = os.path.exists(DB_DIR)
        
        # Test main DB
        main_db_exists = os.path.exists(DB_PATH)
        main_db_accessible = False
        main_count = 0
        main_db_error = None
        
        if main_db_exists:
            try:
                conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM memory")
                main_count = cursor.fetchone()[0]
                conn.close()
                main_db_accessible = True
            except Exception as e:
                main_db_error = str(e)
        
        # Test temp DB
        temp_db_exists = os.path.exists(TEMP_DB_PATH)
        temp_db_accessible = False
        temp_count = 0
        temp_db_error = None
        
        if temp_db_exists:
            try:
                conn_temp = sqlite3.connect(TEMP_DB_PATH, check_same_thread=False)
                cursor_temp = conn_temp.cursor()
                cursor_temp.execute("SELECT COUNT(*) FROM temp_memory")
                temp_count = cursor_temp.fetchone()[0]
                conn_temp.close()
                temp_db_accessible = True
            except Exception as e:
                temp_db_error = str(e)
        
        return jsonify({
            "status": "success",
            "db_directory": {
                "path": DB_DIR,
                "exists": db_dir_exists
            },
            "main_db": {
                "path": DB_PATH,
                "exists": main_db_exists,
                "accessible": main_db_accessible,
                "record_count": main_count if main_db_accessible else "N/A",
                "error": main_db_error if main_db_exists and not main_db_accessible else None
            },
            "temp_db": {
                "path": TEMP_DB_PATH,
                "exists": temp_db_exists,
                "accessible": temp_db_accessible,
                "record_count": temp_count if temp_db_accessible else "N/A",
                "error": temp_db_error if temp_db_exists and not temp_db_accessible else None
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")  # Get session ID or use default

    if not user_message:
        return jsonify({"reply": "Please enter a message."})

    # Store user message in temporary memory
    store_temp_memory(session_id, user_message, "User")

    # Get current mode for this session
    current_mode = get_session_mode(session_id)
    
    # Check for mode change commands
    if user_message.lower() == "mikasa mode":
        set_session_mode(session_id, "mikasa")
        response = "✅ Mikasa is On now ~blink~"
        store_temp_memory(session_id, response, "System")
        return jsonify({"reply": response})
    elif user_message.lower() == "assistant mode":
        set_session_mode(session_id, "assistant")
        response = "✅ Switched to Assistant mode."
        store_temp_memory(session_id, response, "System")
        return jsonify({"reply": response})

    # Check for time/date requests
    time_date_request = re.search(r'\b(what|tell).*\b(time|date|day|today)\b', user_message.lower())
    if time_date_request:
        datetime_info = get_current_datetime()
        
        if re.search(r'\btime\b', user_message.lower()):
            response = f"The current time is {datetime_info['time']}."
        elif re.search(r'\b(date|day|today)\b', user_message.lower()):
            response = f"Today is {datetime_info['date']}."
        else:
            response = f"It's currently {datetime_info['full']}."
            
        # Format response based on current mode
        if current_mode.lower() == "mikasa":
            response = f"~I check my watch and look up at you.~\n{response} Why, do you have somewhere to be? 😏"
        else:
            response = f"⏰ {response}"
            
        store_temp_memory(session_id, response, current_mode.capitalize())
        return jsonify({"reply": response})

    # Get permanent memory (long-term knowledge)
    user_memory = retrieve_memory("Player")

    # Retrieve temporary chat memory
    temp_memory = retrieve_temp_memory(session_id, 20)  # Last 20 messages

    # Handle Memory Commands

    # Handle Memory Commands
    if re.search(r"remember that", user_message, re.IGNORECASE):
        memory_text = user_message.replace("remember that", "").strip()
        success = store_memory("Player", memory_text)
        response = "Alright, Charan. I've saved that for you. 💾" if success else "Hmm... something went wrong while saving it. Want me to try again? 🥺"
        store_temp_memory(session_id, response, current_mode.capitalize())
        return jsonify({"reply": response})
    
    elif re.search(r"remove that", user_message, re.IGNORECASE):
        keyword = user_message.replace("remove that", "").strip()
        count = remove_memory("Player", keyword)
        response = f"All done, Charan. I've cleared {count} memories for you. 🗑️" if count > 0 else "Hmm... I couldn't find any matching memories to delete. 🧐"
        store_temp_memory(session_id, response, current_mode.capitalize())
        return jsonify({"reply": response})
    
    elif re.search(r"update that", user_message, re.IGNORECASE):
        match = re.search(r"update that (.+) to (.+)", user_message, re.IGNORECASE)
        if match:
            old_data, new_data = match.groups()
            update_result = update_memory("Player", old_data.strip(), new_data.strip())
            store_temp_memory(session_id, update_result, current_mode.capitalize())
            return jsonify({"reply": update_result})
        else:
            response = "⚠️ Please use 'update that [old data] to [new data]' format."
            store_temp_memory(session_id, response, current_mode.capitalize())
            return jsonify({"reply": response})
    
    elif user_message.lower() == "del chat":
        if delete_temp_memory(session_id):  # Delete specific session
            return jsonify({"reply": "🧹 All set, Charan. I've wiped the temporary memory like you asked."})
        else:
            return jsonify({"reply": "😕 Something went wrong while clearing it... want me to try again?"})
    
    elif user_message.lower() == "del prev":
        if delete_recent_temp_memory(session_id):  # Delete recent entries
            return jsonify({"reply": ""})  # Return an empty reply
        else:
            response = "⚠️ Error deleting recent chat entries."
            store_temp_memory(session_id, response, current_mode.capitalize())
            return jsonify({"reply": response})

    # Get AI Response with Memory and Context based on the current mode
    bot_reply, source_name = get_ollama_response(user_message, user_memory, temp_memory, current_mode)

    # Store bot reply in temporary memory
    store_temp_memory(session_id, bot_reply, source_name)

    return jsonify({"reply": bot_reply})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)