#!/bin/bash

echo "Starting conversion process..."
start_time=$(date +%s)

curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\11.docx&output=pdf"
echo "------------"
curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\22.xlsx&output=pdf"
echo "------------"
curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\22.xlsx&output=html"
echo "------------"
curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\33.pptx&output=html"
echo "------------"
curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\33.pptx&output=pdf"
echo "------------"

end_time=$(date +%s)
execution_time=$((end_time - start_time))
echo "Conversion process completed."
echo "Total execution time: ${execution_time} seconds"

