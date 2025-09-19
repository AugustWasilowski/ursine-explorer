# Requirements Document

## Introduction

This feature aims to improve the UrsineExplorer ADS-B receiver system by integrating proven techniques and libraries from the ursine-wanderer project (which is based on pyModeS). The current implementation has reliability issues and could benefit from the mature, well-tested approach used in pyModeS for ADS-B message decoding and processing.

## Requirements

### Requirement 1

**User Story:** As an ADS-B operator, I want a reliable and robust ADS-B message decoder that can handle various message formats, so that I can consistently receive and process aircraft data without frequent failures.

#### Acceptance Criteria

1. WHEN the system receives ADS-B messages THEN it SHALL decode them using the proven pyModeS library algorithms
2. WHEN invalid or corrupted messages are received THEN the system SHALL perform CRC validation and reject invalid messages
3. WHEN the system processes messages THEN it SHALL support all standard ADS-B message types (DF4, DF5, DF17, DF18, DF20, DF21)
4. WHEN message decoding fails THEN the system SHALL log the error and continue processing other messages without crashing

### Requirement 2

**User Story:** As an ADS-B operator, I want improved aircraft position calculation and tracking, so that I can get more accurate location data and better track aircraft movements.

#### Acceptance Criteria

1. WHEN receiving position messages THEN the system SHALL use CPR (Compact Position Reporting) decoding algorithms from pyModeS
2. WHEN both even and odd position messages are available THEN the system SHALL calculate global positions accurately
3. WHEN only one position message is available AND a reference position exists THEN the system SHALL calculate local positions within 180NM range
4. WHEN surface position messages are received THEN the system SHALL decode them correctly with appropriate reference positions

### Requirement 3

**User Story:** As an ADS-B operator, I want better message source handling and data input flexibility, so that I can connect to various ADS-B data sources including RTL-SDR, network streams, and dump1090 instances.

#### Acceptance Criteria

1. WHEN connecting to network sources THEN the system SHALL support raw, beast, and other standard formats
2. WHEN connecting to dump1090 THEN the system SHALL handle both JSON output and raw message streams
3. WHEN RTL-SDR is available THEN the system SHALL optionally support direct RTL-SDR connection
4. WHEN connection fails THEN the system SHALL implement proper retry logic and error handling

### Requirement 4

**User Story:** As an ADS-B operator, I want enhanced aircraft data processing and validation, so that I can trust the accuracy of displayed information and filter out erroneous data.

#### Acceptance Criteria

1. WHEN processing aircraft identification messages THEN the system SHALL decode callsigns correctly using pyModeS algorithms
2. WHEN processing velocity messages THEN the system SHALL calculate speed and heading accurately
3. WHEN processing altitude messages THEN the system SHALL handle both barometric and GNSS altitude correctly
4. WHEN duplicate or conflicting data is received THEN the system SHALL implement proper data validation and conflict resolution

### Requirement 5

**User Story:** As an ADS-B operator, I want improved system architecture and modularity, so that the system is easier to maintain, test, and extend with new features.

#### Acceptance Criteria

1. WHEN the system starts THEN it SHALL use a modular architecture separating message decoding, data processing, and display components
2. WHEN adding new message types THEN the system SHALL support easy extension through the pyModeS framework
3. WHEN testing the system THEN it SHALL have comprehensive unit tests for all decoding functions
4. WHEN debugging issues THEN the system SHALL provide detailed logging and diagnostic information

### Requirement 6

**User Story:** As an ADS-B operator, I want backward compatibility with existing configuration and features, so that I can upgrade without losing current functionality like Meshtastic alerts and watchlist monitoring.

#### Acceptance Criteria

1. WHEN upgrading the system THEN it SHALL maintain compatibility with existing config.json format
2. WHEN watchlist aircraft are detected THEN the system SHALL continue to send Meshtastic alerts as before
3. WHEN the dashboard is used THEN it SHALL retain all current display features and controls
4. WHEN the HTTP API is accessed THEN it SHALL continue to provide the same JSON format for aircraft data