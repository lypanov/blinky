#!/bin/bash

# Make the trace directory if it doesn't exist
mkdir -p trace

# Set trace file path
TRACE_FILE="trace/cpu_trace.txt"
ANNOTATED_TRACE_FILE="trace/annotated_trace.txt"

echo "Running CPU test with trace output to $TRACE_FILE..."

# Run the CPU test and redirect output to the trace file
cd "$(dirname "$0")/.."
mill chisel-blinky.test.testOnly gcd.CPUSubset0Test | tee "$TRACE_FILE"

# Check exit status
TEST_STATUS=$?

# Check if the trace file exists
if [ -f "$TRACE_FILE" ]; then
    echo "Trace file generated successfully at $TRACE_FILE"
    
    # Run the trace analyzer
    echo "Analyzing trace file..."
    python3 tools/trace_analyzer.py "$TRACE_FILE"
    
    echo "Done! You can view the annotated trace at $ANNOTATED_TRACE_FILE"
    
    # More precise failure detection - look for actual test failure patterns
    if [ $TEST_STATUS -ne 0 ] || grep -q "Tests: .*failed [1-9]" "$TRACE_FILE" || grep -q "\[FAILED\]" "$TRACE_FILE"; then
        echo ""
        echo "============= TEST FAILED - SHOWING FULL ANNOTATED TRACE ============="
        echo ""
        cat "$ANNOTATED_TRACE_FILE"
        echo ""
        echo "=================================================================="
    else
        echo ""
        echo "============= TEST PASSED - ANNOTATED TRACE AVAILABLE ============="
        echo "You can view the trace at $ANNOTATED_TRACE_FILE"
        echo "=================================================================="
    fi
else
    echo "ERROR: Trace file was not generated. Check if the test ran successfully."
    exit 1
fi 