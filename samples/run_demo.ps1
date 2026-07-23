# Demo: verify an AI answer with one true claim, one false claim, and one unverifiable claim.
python -m sentinel `
  --question "Tell me about the Aurora Solar Array." `
  --answer "The Aurora Solar Array is a solar power station in the Atacama Desert in Chile. It has an installed capacity of 950 megawatts. The plant won an international engineering award in 2021." `
  --sources samples/docs
