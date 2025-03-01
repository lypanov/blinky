#!/bin/bash
DEBUG=1

# Function to display trace files for a given test
display_trace_files() {
    local test_name=$1
    local trace_dir=$2
    
    echo ""
    echo "===== Contents of trace file for '$test_name' ====="
    cat "$trace_dir/cpu_trace_${test_name}.txt"
    echo "===== End of trace file ====="
    
    echo ""
    echo "===== Contents of annotated trace file for '$test_name' ====="
    local annotated_file="$trace_dir/annotated_trace_${test_name}.txt"
    echo "$annotated_file"
    if [ -f "$annotated_file" ]; then
        cat "$annotated_file"
    else
        echo "No annotated trace file found!"
    fi
    echo "===== End of annotated trace file ====="
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [test_name]"
    echo ""
    echo "Arguments:"
    echo "  test_name    Optional: Name of specific test to run (e.g., 'main_loop_test')"
    echo "               If not provided, all tests will be run"
    echo ""
    exit 1
}

# Process command line arguments
TEST_NAME=""
if [ $# -gt 0 ]; then
    if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
        show_usage
    fi
    TEST_NAME="$1"
fi

# Get the absolute path to the project root (parent directory of tools/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Setting CHISEL_CPU_PROJECT_ROOT to: $PROJECT_ROOT"
export CHISEL_CPU_PROJECT_ROOT="$PROJECT_ROOT"

# Create trace directory if it doesn't exist
TRACE_DIR="$PROJECT_ROOT/trace"
mkdir -p "$TRACE_DIR"
echo "Created trace directory at: $TRACE_DIR"

# Always clean up all trace files
echo "Cleaning up trace directory..."
rm -f "$TRACE_DIR/cpu_trace_"*.txt "$TRACE_DIR/annotated_trace_"*.txt "$TRACE_DIR/cpu_stdout_"*.txt "$TRACE_DIR/trace_analyzer_debug_"*.log
echo "Removed all previous trace files"

# Run the tests and capture all output to console log files
echo "Running CPU tests with trace output..."

STDOUT_FILE="$TRACE_DIR/cpu_stdout_all.txt"
if [ -n "$TEST_NAME" ]; then
    echo "Running only test: $TEST_NAME"
    JAVA_OPTS="-DTEST_FILTER=$TEST_NAME" mill chisel-blinky.test.testOnly gcd.CPUSubset0Test | tee "$STDOUT_FILE"
else
    echo "Running all tests..."
    mill chisel-blinky.test.testOnly gcd.CPUSubset0Test | tee "$STDOUT_FILE"
fi


# Save exit code to check test success
TEST_EXIT_CODE=${PIPESTATUS[0]}

# Extract trace information from stdout and merge with trace files if needed

# Check all stdout files for tests that ran
if [ -f "$STDOUT_FILE" ]; then
    # Extract all test sections from stdout using markers
    
    # Get list of test IDs from BEGIN markers
    TEST_IDS=$(grep -o "<<<BEGIN_TEST_OUTPUT:[^<]*<<<" "$STDOUT_FILE" | 
                sed 's/<<<BEGIN_TEST_OUTPUT:\(.*\)<<</\1/')
    
    for TEST_ID in $TEST_IDS; do
        TRACE_FILE="$TRACE_DIR/cpu_trace_${TEST_ID}.txt"
        # Extract relevant trace data between instruction trace marker and END marker
        awk -v test="$TEST_ID" '
            BEGIN { found_test = 0; capturing = 0 }
            /<<<BEGIN_TEST_OUTPUT:.*<<</ {
                if (match($0, /<<<BEGIN_TEST_OUTPUT:(.*?)<<</, arr) && arr[1] == test) {
                    found_test = 1
                    capturing = 1
                }
                next
            }
            found_test && /\[TEST\] Successfully wrote instructions to trace/ {
                capturing = 1;
                next;
            }
            found_test && capturing && />>>END_TEST_OUTPUT>>>/ {
                exit;
            }
            found_test && capturing {
                print;
            }
        ' "$STDOUT_FILE" > "$TRACE_FILE"

        if [ ! -s "$TRACE_FILE" ]; then
            echo "Warning: No trace data extracted for test '$TEST_ID'."
        fi
    done
else
    echo "Error: No stdout file found."
fi

# Process the trace files
echo "Processing trace files..."
if [ -n "$TEST_NAME" ]; then
    # Process only the specific test trace file
    TRACE_FILE="$TRACE_DIR/cpu_trace_${TEST_NAME}.txt"
    if [ -f "$TRACE_FILE" ]; then
        ANNOTATED_TRACE_FILE="$TRACE_DIR/annotated_trace_${TEST_NAME}.txt"
        echo "Analyzing trace file for test '$TEST_NAME'..."
        
        # Examine trace analyzer script
        python3 tools/trace_analyzer.py "$TRACE_FILE" "$ANNOTATED_TRACE_FILE" 2>&1 | tee "$TRACE_DIR/trace_analyzer_debug.log"
        echo "Done! You can view the annotated trace at $ANNOTATED_TRACE_FILE"
        
        # Create symlinks for the default trace files
        ln -sf "cpu_trace_${TEST_NAME}.txt" "$TRACE_DIR/cpu_trace.txt"
        ln -sf "annotated_trace_${TEST_NAME}.txt" "$TRACE_DIR/annotated_trace.txt"
        ln -sf "cpu_stdout_${TEST_NAME}.txt" "$TRACE_DIR/cpu_stdout.txt"
        
        # Check if the annotated trace file looks complete
        if [ -f "$ANNOTATED_TRACE_FILE" ] && ! grep -q "Execution Effects:" "$ANNOTATED_TRACE_FILE"; then
            echo "Warning: The annotated trace file may not contain complete execution information."
            echo "This might indicate that the trace analyzer didn't find all needed data in the trace file."
        fi
    else
        echo "Warning: No trace file found for test '$TEST_NAME'"
    fi
else
    # Process all generated trace files
    for TRACE_FILE in "$TRACE_DIR"/cpu_trace_*.txt; do
        if [ -f "$TRACE_FILE" ]; then
            # Extract test ID from filename
            TEST_ID=$(basename "$TRACE_FILE" .txt | sed 's/cpu_trace_//')
            ANNOTATED_TRACE_FILE="$TRACE_DIR/annotated_trace_${TEST_ID}.txt"
            
            python3 tools/trace_analyzer.py "$TRACE_FILE" "$ANNOTATED_TRACE_FILE"
            
            # Check if the annotated trace file looks complete
            if [ -f "$ANNOTATED_TRACE_FILE" ] && ! grep -q "Execution Effects:" "$ANNOTATED_TRACE_FILE"; then
                echo "Warning: The annotated trace file for '$TEST_ID' may not contain complete execution information."
                echo "This might indicate that the trace analyzer didn't find all needed data in the trace file."
            fi
        fi
    done
    
    # Use the last processed file as the default
    LAST_TRACE=$(ls -t "$TRACE_DIR"/cpu_trace_*.txt 2>/dev/null | head -1)
    if [ -n "$LAST_TRACE" ]; then
        LAST_ID=$(basename "$LAST_TRACE" .txt | sed 's/cpu_trace_//')
        ln -sf "cpu_trace_${LAST_ID}.txt" "$TRACE_DIR/cpu_trace.txt"
        ln -sf "annotated_trace_${LAST_ID}.txt" "$TRACE_DIR/annotated_trace.txt"
        ln -sf "cpu_stdout_all.txt" "$TRACE_DIR/cpu_stdout.txt"
        echo "Created symlinks for default trace files using test '$LAST_ID'"
    fi
fi

# Check if any tests failed
if [ $TEST_EXIT_CODE -ne 0 ]; then
    # Display content of the trace file for debugging
    if [ -n "$TEST_NAME" ]; then
        display_trace_files "$TEST_NAME" "$TRACE_DIR"
    fi

    echo ""
    echo "============= SOME TESTS FAILED ============="
    echo "Check the annotated trace files in the trace directory for details."
    echo "=================================================================="
    
    # Capture the grep output and parse it to extract test names
    FAILED_TESTS=$(grep -ir "FAILED" trace/cpu_*_test.txt)
    echo "$FAILED_TESTS"
    
    # Process each failed test and display its trace files
    echo ""
    echo "Displaying trace files for all failed tests:"
    echo "--------------------------------------------"
    echo "$FAILED_TESTS" | while read -r line; do
        # Extract test name from file path (format: trace/cpu_trace_TESTNAME.txt:[line] - ...)
        if [[ $line =~ trace/cpu_trace_([^.]+)\.txt ]]; then
            test_name="${BASH_REMATCH[1]}"
            echo "Found failed test: $test_name"
            display_trace_files "$test_name" "$TRACE_DIR"
        fi
    done

    exit 1
else
    echo ""
    echo "============= ALL TESTS PASSED ============="
    echo "Annotated traces are available in the trace directory."
    echo "=================================================================="
fi 

# Create a summary of test completion
echo "" 
echo "Test completion summary:"
echo "------------------------"
grep -o "\[TEST_COMPLETION\] .*" "$STDOUT_FILE" | sed 's/\[TEST_COMPLETION\] //'
