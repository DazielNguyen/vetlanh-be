import cloudinary
import cloudinary.uploader
import cloudinary.api

# Configure Cloudinary with your credentials
cloudinary.config(
    cloud_name="dxml1zqnw",
    api_key="179476367576439",
    api_secret="opVMX7tn3qNcIiyEOm2yxylzjqs",
    secure=True,
)

# Step 1 — Upload a sample image
print("Uploading image...")
result = cloudinary.uploader.upload(
    "https://res.cloudinary.com/demo/image/upload/sample.jpg",
    public_id="onboarding_demo",
    overwrite=True,
)

secure_url = result["secure_url"]
public_id = result["public_id"]
print(f"Secure URL : {secure_url}")
print(f"Public ID  : {public_id}")

# Step 2 — Fetch and print image metadata
print("\nFetching image details...")
details = cloudinary.api.resource(public_id)
print(f"Width      : {details['width']} px")
print(f"Height     : {details['height']} px")
print(f"Format     : {details['format']}")
print(f"File size  : {details['bytes']} bytes")

# Step 3 — Generate a transformed URL
# f_auto: Cloudinary automatically picks the best format for the user's browser (e.g. WebP, AVIF)
# q_auto: Cloudinary automatically selects the optimal quality level to balance size vs. clarity
transformed_url = cloudinary.CloudinaryImage(public_id).build_url(
    fetch_format="auto",
    quality="auto",
)

print("\nDone! Click link below to see optimized version of the image. Check the size and the format.")
print(f"Transformed URL: {transformed_url}")
