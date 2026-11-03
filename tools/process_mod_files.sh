#!/bin/bash

# Script to process .Mod files in the tests directory
# It compiles each .Mod file using norebo, then disassembles it

# Get the user's home directory
HOME_DIR="$HOME"

# Check if project-norebo exists
if [ ! -d "$HOME_DIR/ob/project-norebo" ]; then
    echo "Error: project-norebo directory not found at $HOME_DIR/ob/project-norebo"
    echo "Please clone it from: https://github.com/pdewacht/project-norebo.git"
    exit 1
fi

# Set up environment variables
export NOREBO_PATH="$HOME_DIR/ob/project-norebo/Norebo:$HOME_DIR/ob/project-norebo/Oberon:$HOME_DIR/ob/project-norebo/Bootstrap"

# Change to the tests directory
cd "$(dirname "$0")/../core/tests" || exit 1

# Process each .Mod file
for mod_file in *.Mod; do
    # Skip if no .Mod files found
    [ -e "$mod_file" ] || { echo "No .Mod files found in tests directory"; exit 1; }
    
    # Extract the base name without extension
    base_name="${mod_file%.Mod}"
    
    echo "Processing $mod_file..."
    
    # Extract module name from the file (first line should contain MODULE Name;)
    module_name=$(grep -m 1 "MODULE" "$mod_file" | sed -E 's/MODULE\s+([^;]+);.*/\1/')
    
    echo "Compiling and disassembling $module_name"

    # Clear up the stale .rsc file and .smb file
    rm -f "$module_name.rsc"
    rm -f "$module_name.smb"
    
    # Compile the module using norebo
    "$HOME_DIR/ob/project-norebo/norebo" ORP.Compile "$mod_file"
    
    # Check if compilation was successful by looking for .rsc file
    if [ ! -f "$module_name.rsc" ]; then
        echo "Error: Compilation failed for $mod_file"
        exit 1
    fi
    
    # Parse the .rsc file
    ../tools/rsc_parser.py "$module_name.rsc" fixup > input.txt
    
    # Generate assembly
    python3 ../tools/instruction_parser.py > "$base_name.asm"
    
    # Save the code
    mv input.txt "$base_name.code"
    
    # Remove BEGIN and END lines from the code file
    sed -i '/^BEGIN$/d; /^END$/d' "$base_name.code"
    
    echo "Successfully processed $mod_file"
    echo "Output files: $base_name.asm, $base_name.code"
    echo ""
done

../tools/module_loader.py
../tools/image_dump.py final_system.code

echo "All .Mod files processed successfully" 
