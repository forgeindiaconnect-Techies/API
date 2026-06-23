import os
from typing import List, Union, Iterator
from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.processors import TemplateProcessing
from tokenizers.decoders import ByteLevel as ByteLevelDecoder

def train_custom_tokenizer(
    texts_or_files: Union[List[str], Iterator[str]],
    save_path: str,
    vocab_size: int = 16000,
    is_files: bool = True
) -> Tokenizer:
    """
    Trains a Byte-Pair Encoding (BPE) tokenizer from scratch using ByteLevel pre-tokenization.
    ByteLevel pre-tokenization works best for multi-lingual training (like English + Tamil)
    as it splits unicode characters into byte representations, avoiding out-of-vocabulary
    characters for non-ascii tokens.
    """
    # 1. Initialize empty tokenizer with BPE model
    tokenizer = Tokenizer(BPE(unk_token="[UNK]"))
    
    # 2. Configure ByteLevel pre-tokenizer and decoder
    tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=False)
    tokenizer.decoder = ByteLevelDecoder()
    
    # 3. Create trainer with specified config
    special_tokens = ["[UNK]", "[PAD]", "[BOS]", "[EOS]"]
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=special_tokens,
        show_progress=False
    )
    
    # 4. Train tokenizer
    if is_files:
        # Convert any iterator/list of paths into absolute strings
        file_paths = [os.path.abspath(f) for f in texts_or_files]
        tokenizer.train(file_paths, trainer)
    else:
        # Train from inline iterator list
        tokenizer.train_from_iterator(texts_or_files, trainer)
        
    # 5. Configure template post-processor to automatically append BOS and EOS
    bos_id = tokenizer.token_to_id("[BOS]")
    eos_id = tokenizer.token_to_id("[EOS]")
    
    tokenizer.post_processor = TemplateProcessing(
        single="[BOS] $A [EOS]",
        pair="[BOS] $A [EOS] [BOS] $B [EOS]",
        special_tokens=[
            ("[BOS]", bos_id),
            ("[EOS]", eos_id)
        ]
    )
    
    # 6. Save output files
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    tokenizer.save(save_path)
    return tokenizer

def load_custom_tokenizer(tokenizer_path: str) -> Tokenizer:
    """Loads a previously trained tokenizer from file."""
    if not os.path.exists(tokenizer_path):
        raise FileNotFoundError(f"Tokenizer file not found at: {tokenizer_path}")
    return Tokenizer.from_file(tokenizer_path)
