import torch
from torch import nn
import torch.nn.functional as F

class LSTMForecaster(nn.Module):
    def __init__(self, features: int, hidden: int, layers: int, dropout: float):
        super().__init__()
        self.lstm = nn.LSTM(
            features,
            hidden,
            num_layers=layers,
            dropout=dropout if layers > 1 else 0.0,
            batch_first=True,
        )
        self.head = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, hidden // 2), nn.GELU(), nn.Linear(hidden // 2, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        output, _ = self.lstm(x)
        return self.head(output[:, -1]).squeeze(-1)

class CausalConv1d(nn.Conv1d):
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int, dilation: int):
        super().__init__(in_channels, out_channels, kernel_size, dilation=dilation, padding=0)
        self.left_padding = dilation * (kernel_size - 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return super().forward(F.pad(x, (self.left_padding, 0)))

class TCNBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, dilation: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            CausalConv1d(in_channels, out_channels, 3, dilation),
            nn.BatchNorm1d(out_channels),
            nn.GELU(),
            nn.Dropout(dropout),
            CausalConv1d(out_channels, out_channels, 3, dilation),
            nn.BatchNorm1d(out_channels),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.skip = nn.Conv1d(in_channels, out_channels, 1) if in_channels != out_channels else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x) + self.skip(x)

class TCNForecaster(nn.Module):
    def __init__(self, features: int, channels: list[int], dropout: float):
        super().__init__()
        blocks = []
        current = features
        for index, channel in enumerate(channels):
            blocks.append(TCNBlock(current, channel, 2**index, dropout))
            current = channel
        self.blocks = nn.Sequential(*blocks)
        self.head = nn.Sequential(nn.LayerNorm(current), nn.Linear(current, current // 2), nn.GELU(), nn.Linear(current // 2, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = self.blocks(x.transpose(1, 2))[:, :, -1]
        return self.head(hidden).squeeze(-1)

class DenseAutoencoder(nn.Module):
    def __init__(self, sequence_length: int, features: int, hidden: int, latent: int):
        super().__init__()
        width = sequence_length * features
        self.sequence_length = sequence_length
        self.features = features
        self.encoder = nn.Sequential(nn.Linear(width, hidden), nn.GELU(), nn.Linear(hidden, latent))
        self.decoder = nn.Sequential(nn.Linear(latent, hidden), nn.GELU(), nn.Linear(hidden, width))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        flat = x.flatten(1)
        reconstructed = self.decoder(self.encoder(flat))
        return reconstructed.view(-1, self.sequence_length, self.features)

class LSTMAutoencoder(nn.Module):
    def __init__(self, features: int, hidden: int, latent: int):
        super().__init__()
        self.encoder = nn.LSTM(features, hidden, batch_first=True)
        self.to_latent = nn.Linear(hidden, latent)
        self.from_latent = nn.Linear(latent, hidden)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.output = nn.Linear(hidden, features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.encoder(x)
        latent = self.to_latent(hidden[-1])
        repeated = self.from_latent(latent).unsqueeze(1).expand(-1, x.shape[1], -1)
        decoded, _ = self.decoder(repeated)
        return self.output(decoded)
