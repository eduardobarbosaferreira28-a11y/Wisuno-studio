const history = [
  {
    "timestamp": "2026-06-04T13:46:51+00:00",
    "job_id": "c34c53e0-7",
    "job_type": "carousel",
    "status": "done",
    "details": {"topic": "Test Topic", "files": []}
  }
];

let groups = {};
for (const entry of history) {
  const dateObj = new Date(entry.timestamp);
  const dateStr = dateObj.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });
  if (!groups[dateStr]) groups[dateStr] = [];
  groups[dateStr].push(entry);
}

console.log(groups);
