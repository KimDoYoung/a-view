#!/bin/bash

echo "Starting conversion process..."
start_time=$(date +%s)
echo "----------------------------------------------------"
echo "convert"
echo "----------------------------------------------------"
curl "http://localhost:8003/convert?path=c:/tmp/aview/files/11.docx&output=pdf"
echo "------------"
curl "http://localhost:8003/convert?path=c:/tmp/aview/files/22.xlsx&output=html"
echo "------------"
curl "http://localhost:8003/convert?url=http://localhost:8003/aview/files/11.docx&output=pdf"
echo "------------"
curl "http://localhost:8003/convert?url=http://localhost:8003/aview/files/11.docx&output=html"
echo "----------------------------------------------------"
echo "view"
echo "----------------------------------------------------"
curl "http://localhost:8003/view?path=c:/tmp/aview/files/33.pptx"
echo "----------------------------------------------------"
curl "http://localhost:8003/view?url=http://localhost:8003/aview/files/11.docx"

end_time=$(date +%s)
execution_time=$((end_time - start_time))
echo "Conversion process completed."
echo "Total execution time: ${execution_time} seconds"

