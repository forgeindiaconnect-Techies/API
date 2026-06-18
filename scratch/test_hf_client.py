from huggingface_hub import InferenceClient
import traceback

def test_hf_client():
    token = "hf_placeholder_token_for_testing"
    print("Initializing InferenceClient...")
    client = InferenceClient(token=token)
    
    try:
        print("Testing with width=512 and height=512...")
        image = client.text_to_image(
            "A cute dog running in a field", 
            model="black-forest-labs/FLUX.1-schnell",
            width=512,
            height=512
        )
        print(f"Success! Image format: {image.format}, Size: {image.size}")
        image.save("scratch/test_dog_512.png")
    except Exception as e:
        print("Failed with width/height parameters:")
        traceback.print_exc()

if __name__ == "__main__":
    test_hf_client()
