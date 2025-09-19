#!/usr/bin/env python3
"""Quick performance test to verify implementation"""

import sys
import time
sys.path.append('.')

from test_performance_stress_minimal import MockMessageSource, MockADSBDecoder, MockMessageSourceManager

def quick_test():
    print("Running quick performance test...")
    
    # Create source and decoder
    source_manager = MockMessageSourceManager()
    source = MockMessageSource('test', messages_per_second=50, duration_seconds=5)
    source_manager.add_source(source)
    
    decoder = MockADSBDecoder()
    
    # Start processing
    source_manager.start_collection()
    start_time = time.time()
    total_processed = 0
    
    try:
        while time.time() - start_time < 6:
            messages = source_manager.get_message_batch()
            if messages:
                decoder.process_messages(messages)
                total_processed += len(messages)
            time.sleep(0.1)
        
        # Stop and get results
        source_manager.stop_collection()
        
        duration = time.time() - start_time
        rate = total_processed / duration
        stats = decoder.get_statistics()
        
        print(f"Results:")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Messages processed: {total_processed}")
        print(f"  Rate: {rate:.1f} msg/s")
        print(f"  Aircraft tracked: {len(decoder.get_aircraft_data())}")
        print(f"  Decode rate: {stats['decode_rate']:.1%}")
        
        # Basic assertions
        assert total_processed > 100, f"Expected >100 messages, got {total_processed}"
        assert rate > 10, f"Expected >10 msg/s, got {rate:.1f}"
        assert stats['decode_rate'] > 0.8, f"Expected >80% decode rate, got {stats['decode_rate']:.1%}"
        
        print("✅ Quick performance test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        source_manager.stop_collection()

if __name__ == "__main__":
    success = quick_test()
    sys.exit(0 if success else 1)