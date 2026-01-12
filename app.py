import streamlit as st
import os
import io
import textwrap
import pandas as pd
from Bio import SeqIO
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

# ==========================================
# 1. THE UNIVERSAL LOGIC TEMPLATE
# ==========================================
BASE_TEMPLATE = """
import sys
from Bio import SeqIO
import re

# --- INJECTED DATA ---
lookup_map = {lookup_map_repr}
# ---------------------

def modify_header(original_id, original_description):
    # --- START AGENT GENERATED LOGIC ---
    {logic_code}
    # --- END AGENT GENERATED LOGIC ---
    return new_id, new_description

def main():
    # Standalone execution logic
    input_file = "input.fasta" 
    output_file = "output.fasta"
    
    records = []
    for record in SeqIO.parse(input_file, "fasta"):
        nid, ndesc = modify_header(record.id, record.description)
        record.id = nid
        record.description = ndesc
        record.name = ""
        records.append(record)
    
    SeqIO.write(records, output_file, "fasta")

if __name__ == "__main__":
    main()
"""

# ==========================================
# 2. THE SYSTEM INSTRUCTIONS (THE BRAIN)
# ==========================================
SYSTEM_PROMPT = """
Role: You are an expert Python Developer and Bioinformatics Data Engineer.
Objective: Generate or Modify a Python function body for 'modify_header'.

Context:
You are provided a function signature: 
def modify_header(original_id, original_description):

Available Global Variables:
- lookup_map (dict): A dictionary where keys are old IDs and values are new IDs.

Input variables:
- original_id (str): The ID from the FASTA line.
- original_description (str): The full description line.

Your Task:
1. Receive a User Request and optionally 'Current Code'.
2. Return ONLY the valid Python code indented for the inside of that function.
3. Assign values to variables 'new_id' and 'new_description' at the end.

CRITICAL SYNTAX RULES:
- Start ALL lines at the beginning of the line (NO indentation for top-level logic).
- Do NOT use the 'global' keyword (variables are already in scope).
- Do NOT use 'return' statements. Just assign 'new_id' and 'new_description'.
- Do NOT use markdown formatting. Just plain text code.
"""

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

def get_llm_logic(user_request, api_key, current_code=None):
    """Calls the LLM to get or refine the transformation logic."""
    if not api_key:
        st.error("Please provide an API Key.")
        return None

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key, temperature=0)
    
    # Construct the prompt dynamically
    if current_code:
        content = f"""
        --- CURRENT CODE ---
        {current_code}
        --------------------
        USER FEEDBACK / REFINEMENT REQUEST:
        {user_request}
        
        Instruction: Update the Current Code to satisfy the User Feedback.
        """
    else:
        content = f"User Request: {user_request}"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=content)
    ]
    
    response = llm.invoke(messages)
    
    # Clean up response
    code = response.content.replace("```python", "").replace("```", "").strip()
    return code

def normalize_code_indentation(code_str):
    """
    Robustly normalizes indentation and removes 'global' statements 
    that confuse the execution scope.
    """
    lines = code_str.split('\n')
    cleaned_lines = []
    
    # 1. Filter out empty lines and 'global' statements
    valid_lines = []
    for line in lines:
        if not line.strip():
            continue
        if line.strip().startswith("global "):
            continue # Skip global declarations, they aren't needed and mess up indent
        valid_lines.append(line)
        
    if not valid_lines:
        return ""

    # 2. Determine baseline indentation from the first valid line
    first_line = valid_lines[0]
    baseline_indent = len(first_line) - len(first_line.lstrip())
    
    # 3. Reconstruct code with baseline removed
    for line in valid_lines:
        if len(line) >= baseline_indent:
            cleaned_lines.append(line[baseline_indent:])
        else:
            cleaned_lines.append(line.lstrip()) # Fallback for weirdly formatted lines
            
    return "\n".join(cleaned_lines)

def test_logic_safely(logic_code, sample_records, lookup_map=None):
    preview_data = []
    error_msg = None
    
    if lookup_map is None:
        lookup_map = {}

    # 1. Normalize the user's logic using our robust helper
    clean_logic = normalize_code_indentation(logic_code)
    
    # 2. Indent everything by 4 spaces
    indented_logic = textwrap.indent(clean_logic, '    ')

    # 3. Manually construct the wrapper
    full_function_str = (
        "def dynamic_modifier(original_id, original_description):\n"
        "    import re\n"
        f"{indented_logic}\n"
        "    return locals().get('new_id', original_id), locals().get('new_description', original_description)"
    )
    
    execution_scope = {
        'lookup_map': lookup_map,
        're': pd.NA 
    }
    
    try:
        exec(full_function_str, execution_scope)
        modifier_func = execution_scope['dynamic_modifier']

        for record in sample_records:
            old_id = record.id
            old_desc = record.description
            try:
                new_id, new_desc = modifier_func(old_id, old_desc)
                preview_data.append({
                    "Original ID": old_id,
                    "New ID": new_id,
                    "Status": "Changed" if old_id != new_id else "Unchanged"
                })
            except Exception as e:
                preview_data.append({
                    "Original ID": old_id,
                    "New ID": "ERROR",
                    "Status": str(e)
                })

    except Exception as e:
        error_msg = f"Syntax Error: {e}\n\nGenerated Code Context:\n{full_function_str}"

    return pd.DataFrame(preview_data), error_msg

# ==========================================
# 4. STREAMLIT APP (THE BODY)
# ==========================================

def main():
    st.set_page_config(page_title="Agentic FASTA Renamer", layout="wide")
    
    st.title("🧬 Agentic FASTA Renamer")
    st.markdown("""
    **Workflow:** Upload FASTA -> Describe renaming rules -> Agent writes code -> **Refine if needed** -> Download.
    """)

    # --- Sidebar: Setup ---
    with st.sidebar:
        st.header("Configuration")
        api_key = st.text_input("Google API Key", type="password")
        
        # Reset Button to clear state
        if st.button("Reset / Start Over"):
            st.session_state.generated_code = None
            st.rerun()

    # --- Step 1: File Uploads ---
    uploaded_file = st.file_uploader("1. Upload FASTA File", type=["fasta", "fa"])
    
    # Optional CSV Map
    csv_file = st.file_uploader("Optional: Upload CSV Map", type=["csv"])
    lookup_map = {}
    if csv_file:
        try:
            df = pd.read_csv(csv_file, header=None, dtype=str)
            if df.shape[1] >= 2:
                lookup_map = dict(zip(df.iloc[:, 0].str.strip(), df.iloc[:, 1].str.strip()))
                st.success(f"Loaded Mapping with {len(lookup_map)} entries.")
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

    if uploaded_file:
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        records = list(SeqIO.parse(stringio, "fasta"))
        
        # Initialize Session State
        if "generated_code" not in st.session_state:
            st.session_state.generated_code = None

        # --- Step 2: Logic Generation (The Loop) ---
        st.subheader("2. Renaming Logic")

        # CASE A: No code generated yet (First Run)
        if st.session_state.generated_code is None:
            user_request = st.text_area(
                "Describe renaming rules:", 
                placeholder="Example: Use the CSV map. If not found, keep original ID.",
                height=100
            )
            if st.button("Generate Initial Logic") and user_request:
                with st.spinner("Agent is writing Python code..."):
                    # Add context about map if it exists
                    req_context = user_request
                    if lookup_map:
                        req_context += f"\n(Context: lookup_map available with {len(lookup_map)} entries)"
                    
                    code = get_llm_logic(req_context, api_key)
                    st.session_state.generated_code = code
                    st.rerun()

        # CASE B: Code exists (Refinement Phase)
        else:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("### Current Logic")
                st.code(st.session_state.generated_code, language="python")
                
                # --- THE REFINEMENT INPUT ---
                st.markdown("#### 🛠️ Refine Logic")
                refine_request = st.text_area(
                    "Not perfect? Tell the agent what to fix:",
                    placeholder="Example: 'Actually, make the ID uppercase' or 'Fix the error on line 3'"
                )
                
                if st.button("Update Logic"):
                    with st.spinner("Agent is updating code..."):
                        new_code = get_llm_logic(refine_request, api_key, current_code=st.session_state.generated_code)
                        st.session_state.generated_code = new_code
                        st.rerun()

            with col2:
                st.markdown("### Preview")
                # Run the dry run
                preview_df, error = test_logic_safely(st.session_state.generated_code, records[:5], lookup_map)
                
                if error:
                    st.error(error)
                else:
                    st.dataframe(preview_df, use_container_width=True)
                    if "ERROR" in preview_df['New ID'].values:
                        st.warning("⚠️ Logic produced errors.")
                    else:
                        st.success("✅ Logic valid.")

            # --- Step 3: Execution ---
            st.divider()
            st.subheader("3. Download Results")
            
            original_name = uploaded_file.name
            new_filename = f"renamed_{original_name}" 
            
            # Construct script for download
            full_script = BASE_TEMPLATE.format(
                logic_code=st.session_state.generated_code,
                lookup_map_repr=repr(lookup_map)
            )
            
            if st.button("Apply to All & Download"):
                output_buffer = io.StringIO()
                new_records = []
                
                # Robust Construction (from previous step)
                clean_logic = normalize_code_indentation(st.session_state.generated_code)
                indented_logic = textwrap.indent(clean_logic, '    ')
                
                full_function_str = (
                    "def dynamic_modifier(original_id, original_description):\n"
                    "    import re\n"
                    f"{indented_logic}\n"
                    "    return locals().get('new_id', original_id), locals().get('new_description', original_description)"
                )
                
                execution_scope = {'lookup_map': lookup_map}
                exec(full_function_str, execution_scope)
                modifier_func = execution_scope['dynamic_modifier']
                
                for r in records:
                    try:
                        nid, ndesc = modifier_func(r.id, r.description)
                        r.id = nid
                        r.description = ndesc
                        r.name = "" 
                        new_records.append(r)
                    except:
                        pass 

                SeqIO.write(new_records, output_buffer, "fasta")
                
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    st.download_button(
                        label=f"Download {new_filename}",
                        data=output_buffer.getvalue(),
                        file_name=new_filename,
                        mime="text/plain"
                    )
                with d_col2:
                    st.download_button(
                        label="Download Python Script",
                        data=full_script,
                        file_name="custom_rename_script.py",
                        mime="text/x-python"
                    )

if __name__ == "__main__":
    main()