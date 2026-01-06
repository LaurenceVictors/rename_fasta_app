import sys
import re
from Bio import SeqIO

def modify_header(original_id, original_description):
    """
    TRANSFORMATION LOGIC GOES HERE.
    The Agent will rewrite this function based on user input.
    
    Args:
        original_id (str): The ID from the FASTA line (after >).
        original_description (str): The full description line (including ID).
    
    Returns:
        new_id (str): The new ID to write.
        new_description (str): The new description to write (usually same as new_id).
    """
    # --- START AGENT GENERATED LOGIC ---
    
    # Placeholder: Default behavior is to keep it unchanged
    new_id = original_id
    new_description = original_description
    
    # --- END AGENT GENERATED LOGIC ---
    return new_id, new_description

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py <input.fasta> <output.fasta>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    print(f"Processing {input_file}...")
    
    # We use a list to store records to ensure we don't write duplicates if logic is bad
    new_records = []
    
    try:
        for record in SeqIO.parse(input_file, "fasta"):
            # Apply the logic
            new_id, new_desc = modify_header(record.id, record.description)
            
            # Update the record
            record.id = new_id
            record.description = new_desc
            
            # clear name/description to ensure biopython writes the header correctly
            # (Biopython sometimes keeps the old ID in the description if not cleared)
            record.name = "" 
            
            new_records.append(record)

        # Write output
        count = SeqIO.write(new_records, output_file, "fasta")
        print(f"Successfully renamed {count} sequences.")
        print(f"Saved to {output_file}")

    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()