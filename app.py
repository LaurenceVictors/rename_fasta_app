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

def modify_header(original_id, original_description):
    # --- START AGENT GENERATED LOGIC ---
    {logic_code}
    # --- END AGENT GENERATED LOGIC ---
    return new_id, new_description

def main():
    # This block is for the standalone script execution
    input_file = "input.fasta" 
    output_file = "output.fasta"
    # In real usage, sys.argv would handle this.
    pass

if __name__ == "__main__":
    main()
"""

# ==========================================
# 2. THE SYSTEM INSTRUCTIONS (THE BRAIN)
# ==========================================
SYSTEM_PROMPT = """
Role: You are an expert Python Developer and Bioinformatics Data Engineer.
Objective: Generate a Python function body for 'modify_header' to rename FASTA sequences based on user requirements.

Context:
You are provided a function signature: 
def modify_header(original_id, original_description):

Input variables:
- original_id (str): The ID from the FASTA line (after >).
- original_description (str): The full description line.

Your Task:
1. Receive a natural language request (e.g., "Keep only the first part before the underscore").
2. Return ONLY the valid Python code indented for the inside of that function.
3. Assign values to variables 'new_id' and 'new_description' at the end.
4. Do NOT return the function definition line, only the body.
5. Do NOT use markdown formatting (```python). Just plain text code.

Example Output:
parts = original_id.split('_')
if len(parts) > 1:
    new_id = parts[0]
else:
    new_id = original_id
new_description = new_id
"""

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================

def get_llm_logic(user_request, api_key):
    """Calls the LLM to get the transformation logic."""
    if not api_key:
        st.error("Please provide an API Key.")
        return None

    # UPDATED: Using the stable, free-tier friendly model
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key, temperature=0)
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"User Request: {user_request}")
    ]
    
    response = llm.invoke(messages)
    
    # Clean up response (remove markdown if the LLM forgot instructions)
    code = response.content.replace("```python", "").replace("```", "").strip()
    return code

def test_logic_safely(logic_code, sample_records):
    """
    Executes the generated string code in a safe local scope 
    against the sample data to create a preview DataFrame.
    """
    preview_data = []
    error_msg = None

    # UPDATED: Indent the user's code so it fits inside the function wrapper
    indented_logic = textwrap.indent(logic_code, '    ')

    # Wrapper to execute the dynamic code
    full_function_str = f"""
def dynamic_modifier(original_id, original_description):
    import re
    # --- Injected Code starts below ---
{indented_logic}
    # --- Injected Code ends above ---
    # UPDATED: Use locals().get() to safely retrieve variables even if user logic failed to define them
    return locals().get('new_id', original_id), locals().get('new_description', original_description)
"""
    local_scope = {}
    
    try:
        # Compile the function
        exec(full_function_str, {}, local_scope)
        modifier_func = local_scope['dynamic_modifier']

        # Run on samples
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
        error_msg = f"Syntax Error in Generated Code: {e}\n\nCode attempting to run:\n{full_function_str}"

    return pd.DataFrame(preview_data), error_msg

# ==========================================
# 4. STREAMLIT APP (THE BODY)
# ==========================================

def main():
    st.set_page_config(page_title="Agentic FASTA Renamer", layout="wide")
    
    st.title("🧬 Agentic FASTA Renamer")
    st.markdown("""
    **Workflow:** Upload FASTA -> Describe renaming rules -> Agent writes code -> You review -> Download.
    *Uses the 'Universal Logic Template' approach.*
    """)

    # --- Sidebar: Setup ---
    with st.sidebar:
        st.header("Configuration")
        api_key = st.text_input("Google API Key", type="password")
        st.info("This app uses Gemini 2.0 Flash via LangChain.")

    # --- Step 1: File Upload ---
    uploaded_file = st.file_uploader("Upload FASTA File", type=["fasta", "fa"])
    
    if uploaded_file:
        # Load data into memory (using Biopython)
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        records = list(SeqIO.parse(stringio, "fasta"))
        
        st.success(f"Loaded {len(records)} sequences from '{uploaded_file.name}'.")
        
        # Show raw sample
        with st.expander("View Raw File Sample"):
            st.code(uploaded_file.getvalue().decode("utf-8")[:500] + "...")

        # --- Step 2: User Intent ---
        st.subheader("1. Describe Renaming Logic")
        user_request = st.text_area(
            "How should we rename these headers?", 
            placeholder="Example: Remove everything after the first pipe '|' symbol, or add 'human_' to the start.",
            height=100
        )

        generate_btn = st.button("Generate Logic & Preview")

        # Session State management
        if "generated_code" not in st.session_state:
            st.session_state.generated_code = None

        if generate_btn and user_request:
            with st.spinner("Agent is writing Python code..."):
                generated_code = get_llm_logic(user_request, api_key)
                st.session_state.generated_code = generated_code

        # --- Step 3: Human-in-the-Loop Review ---
        if st.session_state.generated_code:
            st.subheader("2. Review & Verify")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Generated Python Logic")
                st.code(st.session_state.generated_code, language="python")
                st.caption("This logic will be injected into the template.")

            with col2:
                st.markdown("### Preview (First 5 Sequences)")
                # Run the dry run
                preview_df, error = test_logic_safely(st.session_state.generated_code, records[:5])
                
                if error:
                    st.error(error)
                else:
                    st.dataframe(preview_df, use_container_width=True)
                    
                    # Validation Check
                    if "ERROR" in preview_df['New ID'].values:
                        st.warning("⚠️ The logic produced errors on some lines. Please refine your request.")
                    elif preview_df['New ID'].duplicated().any():
                        st.error("⚠️ Stop! This logic creates duplicate IDs. This is dangerous.")
                    else:
                        st.success("✅ Logic looks valid and unique.")

            # --- Step 4: Execution ---
            st.subheader("3. Execute & Download")
            
            # UPDATED: Generate dynamic output filename
            original_name = uploaded_file.name
            # If name is 'GLP2.fa', this makes it 'renamed_GLP2.fa'
            new_filename = f"renamed_{original_name}" 
            
            # Construct the full downloadable script
            full_script = BASE_TEMPLATE.format(logic_code=st.session_state.generated_code)
            
            # Apply logic to ALL records for the output file
            if st.button("Apply to All & Download"):
                # Run transformation on all records
                output_buffer = io.StringIO()
                new_records = []
                
                # UPDATED: Re-compile logic with correct indentation
                indented_logic = textwrap.indent(st.session_state.generated_code, '    ')
                
                local_scope = {}
                full_function_str = f"""
def dynamic_modifier(original_id, original_description):
    import re
{indented_logic}
    return locals().get('new_id', original_id), locals().get('new_description', original_description)
"""
                exec(full_function_str, {}, local_scope)
                modifier_func = local_scope['dynamic_modifier']
                
                for r in records:
                    try:
                        nid, ndesc = modifier_func(r.id, r.description)
                        r.id = nid
                        r.description = ndesc
                        r.name = "" # Biopython cleanup
                        new_records.append(r)
                    except:
                        pass # specific error handling if needed

                SeqIO.write(new_records, output_buffer, "fasta")
                
                # Download Buttons
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    st.download_button(
                        label=f"Download {new_filename}",
                        data=output_buffer.getvalue(),
                        file_name=new_filename, # <--- UPDATED HERE
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